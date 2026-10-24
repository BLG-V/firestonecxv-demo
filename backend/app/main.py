"""HTTP interface for the local, entirely synthetic enterprise-chain demo."""

import hmac
import ipaddress
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ai_analysis import AIAnalysisResponse, AnalysisRateLimiter, analyze_profile
from .core import CONFIG, SEGMENTS, connect, enterprise, init_db, positions, profile


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def enforce_verification_access(authorization: str | None) -> None:
    expected = os.getenv("DEMO_VERIFICATION_TOKEN", "").strip()
    if not expected:
        return
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not authorization or not authorization.startswith("Bearer ") or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})


def client_ip_for_limit(request: Request) -> str:
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        try:
            return str(ipaddress.ip_address(real_ip))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


class VerificationSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_id: int = Field(gt=0)
    action: Literal["confirm", "correct", "reject"]
    operator: str = Field(min_length=1, max_length=64)
    corrected_segment_id: str | None = None
    corrected_chain_id: str | None = None
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_correction(self):
        if self.action == "correct" and not self.corrected_segment_id:
            raise ValueError("corrected_segment_id is required for correct")
        return self


class VerificationResponse(BaseModel):
    position_id: int
    enterprise_id: str
    action: Literal["confirm", "correct", "reject"]
    status: Literal["confirmed", "rejected"]
    segment_id: str
    segment_name: str
    verified_by: str
    verified_at: str
    profile: dict[str, object]
    data_mode: Literal["synthetic"]


def create_app(db_path: str | None = None) -> FastAPI:
    require_verification_token = os.getenv("DEMO_REQUIRE_VERIFICATION_TOKEN", "").strip().lower() == "true"
    if require_verification_token and not os.getenv("DEMO_VERIFICATION_TOKEN", "").strip():
        raise RuntimeError("DEMO_VERIFICATION_TOKEN is required when DEMO_REQUIRE_VERIFICATION_TOKEN=true")
    path = db_path or os.getenv("DEMO_DB_PATH") or str(Path(__file__).resolve().parents[1] / "data" / "demo.sqlite3")
    init_db(path)
    app = FastAPI(title="Synthetic Enterprise Chain Demo", version=CONFIG["version"])
    ai_ip_rate_limiter = AnalysisRateLimiter(limit=10, window_seconds=60)
    ai_global_rate_limiter = AnalysisRateLimiter(limit=30, window_seconds=60, max_clients=1)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.get("/api/health")
    def health():
        return {"status": "ok", "data_mode": "synthetic", "data_as_of": CONFIG["demo_as_of"],
                "config_version": CONFIG["version"]}

    @app.get("/api/v1/enterprises")
    def enterprises():
        with connect(path) as conn:
            result = []
            for row in conn.execute("SELECT id FROM enterprises ORDER BY id"):
                card = profile(conn, row["id"])
                item = enterprise(conn, row["id"])
                current = next((p for p in card["where"]["positions"] if p["match_level"] == "primary"), None)
                result.append({"enterprise_id": row["id"], "enterprise_name": item["name"],
                               "home_region": item["home_region"], "primary_segment_name": current["segment_name"] if current else None,
                               "industry": item.get("industry") or (current["segment_name"] if current else None),
                               "position_count": len(card["where"]["positions"]),
                               "icv_score": card["worth"]["icv_score"] if card["worth"] else None,
                               "grade": card["decision"]["grade"] if card["decision"] else None,
                               "decision_status": card["decision_status"], "data_mode": "synthetic"})
            return result

    @app.get("/api/v1/enterprises/{enterprise_id}/chain-profile")
    def chain_profile(enterprise_id: str):
        with connect(path) as conn:
            result = profile(conn, enterprise_id)
        if result is None:
            raise HTTPException(404, "Unknown enterprise")
        return result

    @app.post("/api/v1/enterprises/{enterprise_id}/ai-analysis", response_model=AIAnalysisResponse)
    async def ai_analysis(enterprise_id: str, request: Request):
        client_ip = client_ip_for_limit(request)
        if not ai_ip_rate_limiter.allow(client_ip) or not ai_global_rate_limiter.allow("global"):
            raise HTTPException(status_code=429, detail="AI analysis rate limit exceeded")
        with connect(path) as conn:
            result = profile(conn, enterprise_id)
        if result is None:
            raise HTTPException(404, "Unknown enterprise")
        return await analyze_profile(result)

    def segment_or_404(segment_id: str):
        segment = SEGMENTS.get(segment_id)
        if segment is None:
            raise HTTPException(404, "Unknown segment")
        return segment

    def segment_entries(conn, segment_id: str):
        entries = []
        for row in conn.execute("SELECT id FROM enterprises ORDER BY id"):
            item = enterprise(conn, row["id"])
            card = profile(conn, row["id"])
            for position in card["where"]["positions"]:
                if position["segment_id"] != segment_id:
                    continue
                entries.append({"enterprise_id": item["id"], "enterprise_name": item["name"],
                                "home_region": item["home_region"], "leader": item["leader"],
                                "position_id": position["position_id"], "match_level": position["match_level"],
                                "match_score": position["match_score"], "score_kind": position["score_kind"],
                                "status": position["status"], "evidence": position["evidence"],
                                "icv_score": card["worth"]["icv_score"] if card["worth"] else None,
                                "decision_status": card["decision_status"],
                                "attractiveness": card["decision"]["attractiveness"] if card["decision"] else None,
                                "grade": card["decision"]["grade"] if card["decision"] else None,
                                "data_mode": "synthetic"})
        entries.sort(key=lambda entry: (-(entry["match_score"] * (entry["icv_score"] or 0)), entry["enterprise_id"]))
        return entries

    @app.get("/api/v1/segments/{segment_id}/enterprises")
    def segment_enterprises(segment_id: str, status: Literal["candidate", "confirmed"] | None = None,
                            region: str | None = None):
        segment_or_404(segment_id)
        with connect(path) as conn:
            entries = segment_entries(conn, segment_id)
        return [entry for entry in entries if (status is None or entry["status"] == status)
                and (region is None or entry["home_region"] == region)]

    def gap(conn, segment_id: str):
        segment = SEGMENTS[segment_id]
        entries = segment_entries(conn, segment_id)
        local = [entry for entry in entries if entry["home_region"] == CONFIG["region"]["code"]
                 and entry["status"] == "confirmed" and entry["match_level"] != "potential"]
        count = len({entry["enterprise_id"] for entry in local})
        expected = segment["expected_firm_count"]
        gap_level = "critical" if count == 0 else "high" if count * 2 < expected else "mid" if count < expected else "low" if count == expected else "none"
        candidates = [entry for entry in entries if entry["home_region"] != CONFIG["region"]["code"]
                      and entry["status"] == "confirmed" and entry["match_level"] != "potential"
                      and entry["icv_score"] is not None and entry["grade"] is not None
                      and entry["decision_status"] == "scored"]
        candidates.sort(key=lambda entry: (-(entry["attractiveness"] or 0), entry["enterprise_id"]))
        return {"segment_id": segment_id, "segment_name": segment["name"],
                "region_code": CONFIG["region"]["code"], "period": CONFIG["period"],
                "local_firm_count": count, "expected_firm_count": expected,
                "gap_level": gap_level, "missing_tiers": [segment["gap_profile"]] if count < expected else [],
                "cross_region_candidates": [{"enterprise_id": entry["enterprise_id"],
                                             "enterprise_name": entry["enterprise_name"],
                                             "home_region": entry["home_region"], "icv_score": entry["icv_score"],
                                             "attractiveness": entry["attractiveness"], "grade": entry["grade"],
                                             "has_expansion_signal": (entry["attractiveness"] or 0) > 0,
                                             "top_reason": "虚构演示候选，需人工核验"} for entry in candidates[:5]],
                "data_as_of": CONFIG["demo_as_of"]}

    @app.get("/api/v1/segments/{segment_id}/gap-analysis")
    def gap_analysis(segment_id: str):
        segment_or_404(segment_id)
        with connect(path) as conn:
            return gap(conn, segment_id)

    @app.get("/api/v1/chains/{chain_id}/health")
    def chain_health(chain_id: str):
        if chain_id != CONFIG["chain"]["id"]:
            raise HTTPException(404, "Unknown chain")
        with connect(path) as conn:
            result = []
            for segment in CONFIG["segments"]:
                segment_gap = gap(conn, segment["id"])
                entries = segment_entries(conn, segment["id"])
                local = [entry for entry in entries if entry["home_region"] == CONFIG["region"]["code"]
                         and entry["status"] == "confirmed" and entry["match_level"] != "potential"]
                count = segment_gap["local_firm_count"]
                has_leader = any(entry["leader"] for entry in local)
                health_status = "broken" if count == 0 else "strong" if has_leader else "weak"
                scores = [entry["icv_score"] for entry in local if entry["icv_score"] is not None]
                result.append({"segment_id": segment["id"], "segment_name": segment["name"],
                               "upstream_segment_ids": segment["upstream"], "health_status": health_status,
                               "local_firm_count": count, "has_leader": has_leader,
                               "avg_icv": round(sum(scores) / len(scores), 4) if scores else None,
                               "segment_sv": round(sum(segment["sv_dimensions"][dim] * weight for dim, weight in CONFIG["sv_weights"].items()), 4),
                               "gap_level": segment_gap["gap_level"]})
        return {"chain_id": chain_id, "chain_name": CONFIG["chain"]["name"],
                "region_code": CONFIG["region"]["code"], "period": CONFIG["period"],
                "segments": result,
                "summary": {status + "_count": sum(item["health_status"] == status for item in result)
                            for status in ("broken", "weak", "strong")},
                "data_as_of": CONFIG["demo_as_of"]}

    @app.post("/api/v1/verifications", response_model=VerificationResponse)
    def verify(submission: VerificationSubmission, authorization: str | None = Header(default=None)):
        enforce_verification_access(authorization)
        if submission.corrected_chain_id and submission.corrected_chain_id != CONFIG["chain"]["id"]:
            raise HTTPException(422, "Unknown corrected chain")
        if submission.action == "correct" and submission.corrected_segment_id not in SEGMENTS:
            raise HTTPException(422, "Unknown corrected segment")
        payload = submission.model_dump(exclude={"idempotency_key"})
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        key = submission.idempotency_key
        with connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute("SELECT payload,response_json FROM verification_requests WHERE idempotency_key=?", (key,)).fetchone()
            if previous:
                if previous["payload"] != serialized:
                    raise HTTPException(409, "Idempotency key already used with different payload")
                return json.loads(previous["response_json"])
            row = conn.execute("SELECT * FROM positions WHERE id=?", (submission.position_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Unknown position")
            item = enterprise(conn, row["enterprise_id"])
            current = positions(conn, item, include_rejected=True)
            current_position = next((position for position in current if position["position_id"] == submission.position_id), None)
            if current_position is None:
                raise HTTPException(422, "Evidence did not pass source-text validation")
            status = "rejected" if submission.action == "reject" else "confirmed"
            segment_id = submission.corrected_segment_id if submission.action == "correct" else row["segment_id"]
            match_level = "secondary" if submission.action == "correct" and row["match_level"] == "potential" else row["match_level"]
            method = "manual" if submission.action == "correct" else row["match_method"]
            score = 0.0 if submission.action == "correct" else row["match_score"]
            verified_at = datetime.now(timezone.utc).isoformat()
            conn.execute("""UPDATE positions SET status=?,segment_id=?,match_level=?,match_method=?,match_score=?,verified_by=?,verified_at=?
                            WHERE id=?""", (status, segment_id, match_level, method, score, submission.operator, verified_at, submission.position_id))
            result = {"position_id": submission.position_id, "enterprise_id": item["id"],
                      "action": submission.action, "status": status, "segment_id": segment_id,
                      "segment_name": SEGMENTS[segment_id]["name"], "verified_by": submission.operator,
                      "verified_at": verified_at, "profile": profile(conn, item["id"]), "data_mode": "synthetic"}
            conn.execute("INSERT INTO verification_requests VALUES (?,?,?)",
                         (key, serialized, json.dumps(result, ensure_ascii=False)))
            return result

    return app


app = create_app()

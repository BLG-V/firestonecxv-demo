"""Deterministic, synthetic enterprise-chain demo. No external data or model calls."""

import calendar
import json
import re
import sqlite3
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
SEED = json.loads((HERE / "fixtures" / "enterprises.json").read_text(encoding="utf-8"))
AS_OF = date.fromisoformat(CONFIG["demo_as_of"])
SEGMENTS = {segment["id"]: segment for segment in CONFIG["segments"]}
PATH_PATTERN = re.compile(r"^enterprise(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[[0-9]+\])+$")


def months_before(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, month = divmod(month_index, 12)
    return date(year, month + 1, min(value.day, calendar.monthrange(year, month + 1)[1]))


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _records(enterprise: dict, family: str):
    items = enterprise["facts"].get(family, [])
    if isinstance(items, dict):
        items = [items]
        scalar = True
    else:
        scalar = False
    for index, item in enumerate(items):
        path = f"enterprise.facts.{family}" if scalar else f"enterprise.facts.{family}[{index}]"
        yield path + ".text", item


def _rule_matches(enterprise: dict):
    matches = []
    for segment in CONFIG["segments"]:
        for level, families in (("current", ("business_scope", "products", "patents", "qualifications")),
                                ("potential", ("announcements", "financing_uses"))):
            evidence = []
            families_hit = set()
            for family in families:
                for path, record in _records(enterprise, family):
                    term = next((term for term in segment["terms"] if term in record["text"]), None)
                    if term is None:
                        continue
                    evidence.append({"field_path": path, "field_value": record["text"],
                                     "matched_term": term, "source": record["source"], "as_of": record["as_of"]})
                    families_hit.add(family)
            if len(evidence) >= CONFIG["minimum_evidence"]:
                score = min(0.99, sum(CONFIG["match_signal_weights"][family] for family in sorted(families_hit)))
                matches.append({"segment_id": segment["id"], "kind": level, "score": round(score, 4),
                                "evidence": evidence[:10]})
    current = sorted((m for m in matches if m["kind"] == "current"), key=lambda m: (-m["score"], list(SEGMENTS).index(m["segment_id"])))
    for index, match in enumerate(current):
        match["match_level"] = "primary" if index == 0 else "secondary"
    for match in matches:
        if match["kind"] == "potential":
            match["match_level"] = "potential"
    return current + [m for m in matches if m["kind"] == "potential"]


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS enterprises (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, enterprise_id TEXT NOT NULL,
                segment_id TEXT NOT NULL, match_level TEXT NOT NULL,
                match_score REAL NOT NULL, match_method TEXT NOT NULL,
                status TEXT NOT NULL, evidence_json TEXT NOT NULL,
                verified_by TEXT, verified_at TEXT,
                FOREIGN KEY (enterprise_id) REFERENCES enterprises(id)
            );
            CREATE TABLE IF NOT EXISTS verification_requests (
                idempotency_key TEXT PRIMARY KEY, payload TEXT NOT NULL, response_json TEXT NOT NULL
            );
        """)
        if conn.execute("SELECT COUNT(*) FROM enterprises").fetchone()[0]:
            return
        for enterprise in SEED:
            seeded = {**enterprise,
                      "metric_evidence": {key: {"value": str(value), "source": "虚构企业指标",
                                                "as_of": enterprise["core_as_of"]}
                                          for key, value in enterprise["metrics"].items() if value is not None},
                      "segment_value_profile": {
                          segment["id"]: {dimension: {"value": str(value), "source": f"演示配置 {CONFIG['version']}",
                                                       "as_of": CONFIG["demo_as_of"]}
                                          for dimension, value in segment["sv_dimensions"].items()}
                          for segment in CONFIG["segments"]}}
            conn.execute("INSERT INTO enterprises VALUES (?, ?)", (enterprise["id"], json.dumps(seeded, ensure_ascii=False)))
            for match in _rule_matches(enterprise):
                confirmed = enterprise["auto_confirm"] and match["match_level"] != "potential"
                conn.execute("""INSERT INTO positions
                    (enterprise_id,segment_id,match_level,match_score,match_method,status,evidence_json,verified_by,verified_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (enterprise["id"], match["segment_id"], match["match_level"], match["score"], "rule",
                     "confirmed" if confirmed else "candidate", json.dumps(match["evidence"], ensure_ascii=False),
                     "synthetic_seed" if confirmed else None, CONFIG["demo_as_of"] + "T00:00:00Z" if confirmed else None))


def enterprise(conn: sqlite3.Connection, enterprise_id: str) -> dict | None:
    row = conn.execute("SELECT payload FROM enterprises WHERE id=?", (enterprise_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def _resolve(enterprise_data: dict, field_path: str):
    if not PATH_PATTERN.fullmatch(field_path):
        raise ValueError("Invalid evidence path")
    tokens = field_path.replace("[", ".").replace("]", "").split(".")[1:]
    value = enterprise_data
    for token in tokens:
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def valid_evidence(enterprise_data: dict, evidence: list) -> bool:
    if len(evidence) < CONFIG["minimum_evidence"]:
        return False
    paths = set()
    try:
        for item in evidence:
            path = item["field_path"]
            raw = _resolve(enterprise_data, path)
            record = _resolve(enterprise_data, path.rsplit(".", 1)[0])
            raw_text = raw if isinstance(raw, str) else str(raw)
            if not item["field_value"] or item["field_value"] not in raw_text:
                return False
            if item["source"] != record["source"] or item["as_of"] != record["as_of"]:
                return False
            if not item["source"] or not item["as_of"] or date.fromisoformat(item["as_of"]) > AS_OF:
                return False
            if item.get("matched_term") and item["matched_term"] not in item["field_value"]:
                return False
            paths.add(path)
    except (ValueError, KeyError, IndexError, TypeError):
        return False
    return len(paths) >= CONFIG["minimum_evidence"]


def factor_sources_valid(enterprise_data: dict, factors: list[dict]) -> bool:
    try:
        for factor in factors:
            raw = _resolve(enterprise_data, factor["source_field"])
            record = _resolve(enterprise_data, factor["source_field"].rsplit(".", 1)[0])
            if str(raw) != factor["source_value"]:
                return False
            if record["source"] != factor["source"] or record["as_of"] != factor["as_of"]:
                return False
            if date.fromisoformat(factor["as_of"]) > AS_OF:
                return False
    except (ValueError, KeyError, IndexError, TypeError):
        return False
    return True


def positions(conn: sqlite3.Connection, enterprise_data: dict, *, include_rejected: bool = False) -> list[dict]:
    rows = conn.execute("SELECT * FROM positions WHERE enterprise_id=? ORDER BY id", (enterprise_data["id"],)).fetchall()
    result = []
    for row in rows:
        if row["status"] == "rejected" and not include_rejected:
            continue
        evidence = json.loads(row["evidence_json"])
        if not valid_evidence(enterprise_data, evidence):
            continue
        segment = SEGMENTS[row["segment_id"]]
        result.append({"position_id": row["id"], "chain_id": CONFIG["chain"]["id"],
                       "chain_name": CONFIG["chain"]["name"], "segment_id": row["segment_id"],
                       "segment_name": segment["name"], "match_level": row["match_level"],
                       "match_score": row["match_score"],
                       "score_kind": "manual" if row["match_method"] == "manual" else "rule_score",
                       "match_method": row["match_method"], "status": row["status"],
                       "verified_by": row["verified_by"], "verified_at": row["verified_at"], "evidence": evidence})
    return result


def data_issue(enterprise_data: dict, confirmed: list[dict]) -> tuple[str | None, list[dict]]:
    if not confirmed:
        return "no_confirmed_current_position", []
    if date.fromisoformat(enterprise_data["core_as_of"]) < months_before(AS_OF, CONFIG["stale_months"]):
        return "data_stale", [{"missing_field": "核心企业数据已超期", "impact": "超过18个月，不给评分与档位"}]
    missing = [key for key in CONFIG["cf_weights"] if enterprise_data["metrics"].get(key) is None]
    missing += [key for key in CONFIG["fm_weights"] if enterprise_data["fm"].get(key) is None]
    if missing:
        return "missing_data", [{"missing_field": field, "impact": "关键因子缺失，不给评分与档位"} for field in missing]
    return None, []


def _factor(name: str, dimension: str, raw, weight: float, contribution: float, path: str, source: str, as_of: str):
    value = str(raw)
    return {"factor_name": name, "dimension": dimension, "raw_value": raw,
            "normalized_value": round(raw / 100, 4) if dimension in CONFIG["sv_weights"] else raw if isinstance(raw, (float, int)) else None,
            "weight": round(weight, 6), "contribution": round(contribution, 6),
            "direction": "negative" if contribution < 0 else "positive" if contribution > 0 else "neutral",
            "source_field": path, "source_value": value, "source": source, "as_of": as_of,
            "config_version": CONFIG["version"]}


def calculate_worth(enterprise_data: dict, all_positions: list[dict]):
    confirmed = [p for p in all_positions if p["status"] == "confirmed" and p["match_level"] != "potential"]
    issue, gaps = data_issue(enterprise_data, confirmed)
    if issue:
        return None, issue, gaps
    total_weight = sum(CONFIG["position_weights"][p["match_level"]] for p in confirmed)
    segment_sv = 0.0
    sv_factors = []
    for position in confirmed:
        segment = SEGMENTS[position["segment_id"]]
        position_share = CONFIG["position_weights"][position["match_level"]] / total_weight
        for dimension, weight in CONFIG["sv_weights"].items():
            raw = segment["sv_dimensions"][dimension]
            portion = position_share * weight * raw
            segment_sv += portion
            sv_factors.append(_factor(f"{segment['name']}·{dimension}", dimension, raw, position_share * weight,
                                      portion * 0.4, f"enterprise.segment_value_profile.{segment['id']}.{dimension}.value",
                                      f"演示配置 {CONFIG['version']}", CONFIG["demo_as_of"]))
    cf_base = sum(CONFIG["cf_weights"][key] * enterprise_data["metrics"][key] for key in CONFIG["cf_weights"])
    cf = 0.4 + 1.2 * cf_base
    risk_items = enterprise_data["risks"]
    rd = min((CONFIG["risk_rd"].get(item["code"], 1.0) for item in risk_items), default=1.0)
    icv = segment_sv * cf * rd
    cf_factors = [_factor(f"企业竞争力·{key}", key, enterprise_data["metrics"][key], weight,
                          segment_sv * 1.2 * weight * enterprise_data["metrics"][key],
                          f"enterprise.metric_evidence.{key}.value", "虚构企业指标", enterprise_data["core_as_of"])
                  for key, weight in CONFIG["cf_weights"].items()]
    factors = sv_factors + cf_factors
    if rd < 1:
        worst_index = next(i for i, item in enumerate(risk_items) if CONFIG["risk_rd"].get(item["code"], 1.0) == rd)
        risk = risk_items[worst_index]
        factors.append(_factor("风险折减", "risk", risk["detail"], 1 - rd,
                               -segment_sv * cf * (1 - rd), f"enterprise.risks[{worst_index}].detail",
                               risk["source"], risk["as_of"]))
    if not factor_sources_valid(enterprise_data, factors):
        return None, "evidence_mismatch", [{"missing_field": "因子来源与原文不一致", "impact": "拒绝评分，待核验来源"}]
    if abs(sum(f["contribution"] for f in factors) - icv) > 0.1:
        raise ValueError("Factor contributions do not reconcile")
    primary = next((p for p in confirmed if p["match_level"] == "primary"), confirmed[0])
    worth = {"icv_score": round(icv, 4), "segment_sv": round(segment_sv, 4),
             "sv_dimensions": SEGMENTS[primary["segment_id"]]["sv_dimensions"],
             "firm_cf": round(cf, 4), "risk_rd": rd, "factor_breakdown": factors,
             "baseline": 0, "period": CONFIG["period"], "rank_in_segment": None,
             "rank_total": None, "config_version": CONFIG["version"]}
    return worth, None, gaps


def _vetoes(enterprise_data: dict) -> list[dict]:
    hits = []
    for index, risk in enumerate(enterprise_data["risks"]):
        rule = next((rule for rule in CONFIG["veto_rules"] if rule["rule_id"] == risk["code"]), None)
        if rule:
            hits.append({"rule_id": rule["rule_id"], "rule_name": rule["rule_name"],
                         "detail": risk["detail"], "impact": rule["impact"],
                         "evidence": [{"field_path": f"enterprise.risks[{index}].detail", "field_value": risk["detail"],
                                       "source": risk["source"], "as_of": risk["as_of"]}]})
    return hits


def decision(enterprise_data: dict, worth: dict) -> dict:
    cutoff = months_before(AS_OF, 12)
    signals = []
    for event in enterprise_data["signals"]:
        if cutoff <= date.fromisoformat(event["occurred_at"]) <= AS_OF:
            signals.append({**event, "weight": CONFIG["lp_signal_weights"][event["signal_type"]]})
    lp = min(1.0, sum(item["weight"] for item in signals))
    fm = sum(CONFIG["fm_weights"][key] * enterprise_data["fm"][key] for key in CONFIG["fm_weights"])
    attractiveness = worth["icv_score"] * lp * fm
    grade = next((grade for grade in ("S", "A", "B") if attractiveness >= CONFIG["grade_thresholds"][grade]), "C")
    vetoes = _vetoes(enterprise_data)
    if vetoes:
        grade = "C"
    return {"decision_type": "invest_promotion", "grade": grade,
            "attractiveness": round(attractiveness, 4), "landing_prob": round(lp, 4),
            "carrier_match": round(fm, 4), "carrier_match_detail": "虚构供应缺口/载体/政策三项配置加权",
            "expansion_signals": signals, "vetoes": vetoes}


def score_snapshot(enterprise_data: dict, worth: dict, result: dict) -> dict:
    return {"enterprise_id": enterprise_data["id"], "enterprise_name": enterprise_data["name"],
            "chain_id": CONFIG["chain"]["id"], "period": CONFIG["period"],
            "region_code": CONFIG["region"]["code"],
            "decision_status": "vetoed" if result["vetoes"] else "scored",
            "icv_score": worth["icv_score"], "baseline": worth["baseline"],
            "segment_sv": worth["segment_sv"], "firm_cf": worth["firm_cf"], "risk_rd": worth["risk_rd"],
            "rank_in_segment": worth["rank_in_segment"], "rank_total": worth["rank_total"],
            "decision_type": result["decision_type"], "grade": result["grade"],
            "attractiveness": result["attractiveness"], "landing_prob": result["landing_prob"],
            "carrier_match": result["carrier_match"], "expansion_signals": result["expansion_signals"],
            "factor_breakdown": worth["factor_breakdown"], "vetoes": result["vetoes"],
            "data_gaps": [], "data_stale": False, "data_as_of": CONFIG["demo_as_of"],
            "config_version": CONFIG["version"]}


def _explanation(snapshot: dict) -> dict:
    factors = sorted(snapshot["factor_breakdown"], key=lambda f: (-abs(f["contribution"]), f["factor_name"]))
    drivers = []
    for factor in factors[:6]:
        drivers.append({"factor_name": factor["factor_name"], "contribution": factor["contribution"],
                        "direction": factor["direction"], "raw_value": factor["raw_value"],
                        "normalized_value": factor["normalized_value"], "weight": factor["weight"],
                        "human_readable_explanation": f"该演示因子按配置参与计算，对产业链价值分贡献 {factor['contribution']} 分。",
                        "evidence": [{"field_path": factor["source_field"], "field_value": factor["source_value"],
                                      "source": factor["source"], "as_of": factor["as_of"]}]})
    grade = snapshot["grade"]
    action = {"S": "优先安排人工对接", "A": "安排主动核验", "B": "纳入后续跟踪", "C": "先核验风险与数据"}[grade]
    return {"conclusion": f"演示招商档位 {grade}，建议{action}；此结果仅用于离线流程验证。",
            "score_summary": {"score": snapshot["icv_score"], "baseline": snapshot["baseline"],
                              "rank_in_segment": snapshot["rank_in_segment"], "rank_total": snapshot["rank_total"],
                              "summary_text": "全量因子在 worth.factor_breakdown 中，可由原始配置和虚构指标复算。"},
            "drivers": drivers, "vetoes": snapshot["vetoes"], "data_gaps": snapshot["data_gaps"],
            "suggested_actions": [action],
            "next_check_point": {"suggested_date": "2027-01-23", "trigger_conditions": ["扩张事件变化", "风险状态变化"]}}


def profile(conn: sqlite3.Connection, enterprise_id: str) -> dict | None:
    item = enterprise(conn, enterprise_id)
    if item is None:
        return None
    item_positions = positions(conn, item)
    worth, issue, gaps = calculate_worth(item, item_positions)
    if worth is not None:
        scored = []
        for row in conn.execute("SELECT payload FROM enterprises ORDER BY id"):
            other = json.loads(row["payload"])
            other_positions = positions(conn, other)
            other_worth, _, _ = calculate_worth(other, other_positions)
            if other_worth is not None:
                primary = next((p["segment_id"] for p in other_positions if p["status"] == "confirmed" and p["match_level"] == "primary"), None)
                scored.append((other["id"], primary, other_worth["icv_score"]))
        scored.sort(key=lambda item: (-item[2], item[0]))
        worth["rank_total"] = 1 + next(i for i, row in enumerate(scored) if row[0] == enterprise_id)
        own_primary = next((p["segment_id"] for p in item_positions if p["status"] == "confirmed" and p["match_level"] == "primary"), None)
        segment_peers = [row for row in scored if row[1] == own_primary]
        worth["rank_in_segment"] = 1 + next(i for i, row in enumerate(segment_peers) if row[0] == enterprise_id)
        decision_result = decision(item, worth)
        explanation = _explanation(score_snapshot(item, worth, decision_result))
        decision_status = "vetoed" if decision_result["vetoes"] else "scored"
    elif issue in ("missing_data", "data_stale", "evidence_mismatch"):
        decision_result = {"decision_type": "invest_promotion", "grade": None,
                           "attractiveness": None, "landing_prob": None, "carrier_match": None,
                           "carrier_match_detail": None, "expansion_signals": [], "vetoes": _vetoes(item),
                           }
        explanation = None
        decision_status = "data_pending"
    else:
        decision_result = explanation = None
        decision_status = "data_pending"
    abstained = not item_positions
    return {"enterprise_id": item["id"], "enterprise_name": item["name"],
            "where": {"positions": item_positions, "abstained": abstained,
                      "abstain_reason": "不足两条可回查证据，规则弃权" if abstained else None,
                      "missing_signals": ["第二条独立证据"] if abstained else []},
            "worth": worth,
            "decision": decision_result, "decision_status": decision_status,
            "explanation": explanation, "data_as_of": CONFIG["demo_as_of"],
            "data_stale": issue == "data_stale",
            "data_gaps": [gap["missing_field"] for gap in gaps],
            "data_mode": "synthetic", "config_version": CONFIG["version"]}

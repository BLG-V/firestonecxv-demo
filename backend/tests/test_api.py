import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft7Validator

from app.core import SEED, calculate_worth, connect, enterprise, factor_sources_valid, positions, score_snapshot, valid_evidence
from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_VERIFICATION_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_REQUIRE_VERIFICATION_TOKEN", raising=False)
    return TestClient(create_app(str(tmp_path / "demo.sqlite3")))


@pytest.fixture(scope="module")
def schema():
    path = Path(__file__).resolve().parents[2] / "docs" / "enterprise_chain_profile.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate(schema, definition, payload):
    wrapper = {"$schema": schema["$schema"], "definitions": schema["definitions"],
                "$ref": f"#/definitions/{definition}"}
    errors = list(Draft7Validator(wrapper).iter_errors(payload))
    assert not errors, "\n".join(error.message for error in errors)


def test_health_and_enterprise_index_are_synthetic(client):
    health = client.get("/api/health").json()
    assert health == {"status": "ok", "data_mode": "synthetic", "data_as_of": "2026-10-23", "config_version": "demo-1"}
    enterprises = client.get("/api/v1/enterprises").json()
    assert len(enterprises) == 10
    assert all(item["data_mode"] == "synthetic" for item in enterprises)


def test_verification_token_requirement_is_opt_in_and_fails_fast_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_VERIFICATION_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_REQUIRE_VERIFICATION_TOKEN", raising=False)
    create_app(str(tmp_path / "local.sqlite3"))

    monkeypatch.setenv("DEMO_REQUIRE_VERIFICATION_TOKEN", "true")
    with pytest.raises(RuntimeError, match="DEMO_VERIFICATION_TOKEN is required"):
        create_app(str(tmp_path / "public.sqlite3"))


def test_enterprise_index_exposes_searchable_industry(client):
    enterprises = client.get("/api/v1/enterprises").json()

    assert all(item["industry"] == item["primary_segment_name"] for item in enterprises)


def test_profiles_cover_scored_vetoed_pending_stale_missing_and_abstain(client, schema):
    expected = {"e01": "scored", "e05": "vetoed", "e06": "data_pending",
                "e07": "data_pending", "e03": "data_pending", "e04": "data_pending"}
    profiles = {}
    for enterprise_id in [f"e{i:02}" for i in range(1, 11)]:
        response = client.get(f"/api/v1/enterprises/{enterprise_id}/chain-profile")
        assert response.status_code == 200
        item = response.json()
        validate(schema, "EnterpriseChainProfile", item)
        profiles[enterprise_id] = item
    for enterprise_id, status in expected.items():
        assert profiles[enterprise_id]["decision_status"] == status
    assert profiles["e05"]["decision"]["grade"] == "C"
    assert profiles["e06"]["data_stale"] is True and profiles["e06"]["decision"]["grade"] is None
    assert profiles["e07"]["worth"] is None and profiles["e07"]["decision"]["grade"] is None
    assert profiles["e03"]["where"]["abstained"] is True
    assert profiles["e04"]["where"]["positions"][0]["match_level"] == "potential"
    assert profiles["e04"]["worth"] is None
    assert all(position["status"] != "confirmed" for position in profiles["e04"]["where"]["positions"])


def test_evidence_is_exact_source_backed_and_two_items_minimum():
    sample = SEED[0]
    match = next(item for item in __import__("app.core", fromlist=["_rule_matches"])._rule_matches(sample)
                 if item["segment_id"] == "cells")
    assert valid_evidence(sample, match["evidence"])
    forged = [dict(item) for item in match["evidence"]]
    forged[0]["field_value"] += " invented"
    assert not valid_evidence(sample, forged)
    assert not valid_evidence(sample, match["evidence"][:1])
    stale_source = [dict(item) for item in match["evidence"]]
    stale_source[0]["source"] = "unrelated source"
    assert not valid_evidence(sample, stale_source)


def test_factor_ledger_recomputes_score_and_has_more_than_top_six(client, tmp_path):
    with connect(str(tmp_path / "demo.sqlite3")) as conn:
        sample = enterprise(conn, "e01")
        worth, issue, _ = calculate_worth(sample, positions(conn, sample))
    assert issue is None
    assert len(worth["factor_breakdown"]) > 6
    assert factor_sources_valid(sample, worth["factor_breakdown"])
    assert abs(worth["baseline"] + sum(item["contribution"] for item in worth["factor_breakdown"])
               - worth["icv_score"]) <= 0.1
    public = client.get("/api/v1/enterprises/e01/chain-profile").json()["worth"]
    assert public["factor_breakdown"] == worth["factor_breakdown"]


def test_full_score_snapshot_contains_vetoes_and_validates(client, schema, tmp_path):
    with connect(str(tmp_path / "demo.sqlite3")) as conn:
        for enterprise_id in ("e01", "e05"):
            card = client.get(f"/api/v1/enterprises/{enterprise_id}/chain-profile").json()
            snapshot = score_snapshot(enterprise(conn, enterprise_id), card["worth"], card["decision"])
            validate(schema, "ScoreSnapshot", snapshot)
            assert abs(snapshot["baseline"] + sum(factor["contribution"] for factor in snapshot["factor_breakdown"])
                       - snapshot["icv_score"]) <= 0.1
            assert bool(snapshot["vetoes"]) == (enterprise_id == "e05")


def test_graph_and_gap_responses_follow_schema(client, schema):
    health = client.get("/api/v1/chains/nev/health").json()
    validate(schema, "ChainHealth", health)
    gap = client.get("/api/v1/segments/materials/gap-analysis").json()
    validate(schema, "SegmentGapAnalysis", gap)
    cell_gap = client.get("/api/v1/segments/cells/gap-analysis").json()
    validate(schema, "SegmentGapAnalysis", cell_gap)
    assert "e05" not in {item["enterprise_id"] for item in cell_gap["cross_region_candidates"]}
    entries = client.get("/api/v1/segments/equipment/enterprises").json()
    assert entries and all(len(item["evidence"]) >= 2 for item in entries)


def test_verification_is_persistent_immediate_and_idempotent(client, schema):
    before = client.get("/api/v1/enterprises/e02/chain-profile").json()
    position = before["where"]["positions"][0]
    body = {"position_id": position["position_id"], "action": "correct", "operator": "demo-reviewer",
            "corrected_segment_id": "cells", "reason": "synthetic correction", "idempotency_key": "correction-1"}
    first = client.post("/api/v1/verifications", json=body)
    assert first.status_code == 200
    assert first.json()["data_mode"] == "synthetic"
    assert first.json()["profile"]["enterprise_id"] == "e02"
    after = client.get("/api/v1/enterprises/e02/chain-profile").json()
    validate(schema, "EnterpriseChainProfile", after)
    assert after["where"]["positions"][0]["segment_id"] == "cells"
    assert after["where"]["positions"][0]["match_method"] == "manual"
    assert after["where"]["positions"][0]["score_kind"] == "manual"
    assert after["worth"] is not None
    validate(schema, "EnterpriseChainProfile", after)
    duplicate = client.post("/api/v1/verifications", json=body)
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()
    conflict = client.post("/api/v1/verifications", json={**body, "operator": "other"})
    assert conflict.status_code == 409


def test_verification_rejects_unsupported_evidence_feedback(client, schema):
    position = client.get("/api/v1/enterprises/e02/chain-profile").json()["where"]["positions"][0]
    body = {"position_id": position["position_id"], "action": "confirm", "operator": "demo",
            "idempotency_key": "unsupported-feedback", "evidence_position_ids": [1]}
    response = client.post("/api/v1/verifications", json=body)
    assert response.status_code == 422
    assert "evidence_position_ids" not in schema["definitions"]["VerificationSubmission"]["properties"]


def test_verification_requires_idempotency_key(client, schema):
    position = client.get("/api/v1/enterprises/e02/chain-profile").json()["where"]["positions"][0]
    body = {"position_id": position["position_id"], "action": "confirm", "operator": "demo"}

    response = client.post("/api/v1/verifications", json=body)

    assert response.status_code == 422
    assert "idempotency_key" in {item["loc"][-1] for item in response.json()["detail"]}
    assert "idempotency_key" in schema["definitions"]["VerificationSubmission"]["required"]


def test_sequential_verifications_with_distinct_keys_return_current_result(client):
    position = client.get("/api/v1/enterprises/e02/chain-profile").json()["where"]["positions"][0]
    position_id = position["position_id"]
    base = {"position_id": position_id, "operator": "demo-reviewer"}

    confirmed_first = client.post("/api/v1/verifications", json={
        **base, "action": "confirm", "idempotency_key": "confirm-first",
    }).json()
    rejected = client.post("/api/v1/verifications", json={
        **base, "action": "reject", "idempotency_key": "reject-second",
    }).json()
    confirmed_again = client.post("/api/v1/verifications", json={
        **base, "action": "confirm", "idempotency_key": "confirm-third",
    }).json()
    current = client.get("/api/v1/enterprises/e02/chain-profile").json()
    current_position = next(item for item in current["where"]["positions"] if item["position_id"] == position_id)

    assert confirmed_first["status"] == "confirmed"
    assert rejected["status"] == "rejected"
    assert confirmed_again["status"] == "confirmed"
    assert confirmed_again["verified_at"] == current_position["verified_at"]
    assert confirmed_again["verified_at"] != confirmed_first["verified_at"]


def test_concurrent_verifications_with_same_key_are_replayed(client):
    position = client.get("/api/v1/enterprises/e02/chain-profile").json()["where"]["positions"][0]
    body = {"position_id": position["position_id"], "action": "confirm", "operator": "demo-reviewer",
            "idempotency_key": "concurrent-confirm"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post("/api/v1/verifications", json=body), range(2)))

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()


def test_correcting_potential_position_promotes_it_to_secondary(client, schema):
    before = client.get("/api/v1/enterprises/e04/chain-profile").json()
    position = before["where"]["positions"][0]
    assert position["match_level"] == "potential"
    response = client.post("/api/v1/verifications", json={
        "position_id": position["position_id"], "action": "correct", "operator": "demo-reviewer",
        "corrected_segment_id": "materials", "idempotency_key": "promote-potential",
    })

    assert response.status_code == 200
    after = response.json()["profile"]
    validate(schema, "EnterpriseChainProfile", after)
    corrected = next(item for item in after["where"]["positions"] if item["position_id"] == position["position_id"])
    assert corrected["match_level"] == "secondary"
    assert corrected["match_method"] == "manual"
    assert corrected["score_kind"] == "manual"
    assert corrected["status"] == "confirmed"
    assert after["worth"] is not None
    assert any(item["enterprise_id"] == "e04" for item in
               client.get("/api/v1/segments/materials/enterprises?status=confirmed").json())


def test_tampered_position_evidence_abstains_and_tampered_factor_blocks_score(client, tmp_path):
    database = str(tmp_path / "demo.sqlite3")
    card = client.get("/api/v1/enterprises/e09/chain-profile").json()
    position_id = card["where"]["positions"][0]["position_id"]
    with connect(database) as conn:
        evidence = json.loads(conn.execute("SELECT evidence_json FROM positions WHERE id=?", (position_id,)).fetchone()[0])
        evidence[0]["field_value"] = "invented text"
        conn.execute("UPDATE positions SET evidence_json=? WHERE id=?", (json.dumps(evidence), position_id))
    invalid = client.get("/api/v1/enterprises/e09/chain-profile").json()
    assert invalid["where"]["abstained"] is True
    assert invalid["worth"] is None and invalid["decision"] is None
    with connect(database) as conn:
        item = enterprise(conn, "e10")
        item["metric_evidence"]["scale"]["value"] = "0.99"
        conn.execute("UPDATE enterprises SET payload=? WHERE id=?", (json.dumps(item, ensure_ascii=False), "e10"))
    invalid_factor = client.get("/api/v1/enterprises/e10/chain-profile").json()
    assert invalid_factor["decision_status"] == "data_pending"
    assert invalid_factor["worth"] is None
    assert invalid_factor["decision"]["grade"] is None


def test_invalid_correction_is_rejected(client):
    position = client.get("/api/v1/enterprises/e02/chain-profile").json()["where"]["positions"][0]
    missing_segment = client.post("/api/v1/verifications",
                                  json={"position_id": position["position_id"], "action": "correct",
                                        "operator": "demo", "idempotency_key": "missing-segment"})
    assert missing_segment.status_code == 422
    unknown_segment = client.post("/api/v1/verifications",
                                  json={"position_id": position["position_id"], "action": "correct",
                                        "operator": "demo", "corrected_segment_id": "unknown",
                                        "idempotency_key": "unknown-segment"})
    assert unknown_segment.status_code == 422

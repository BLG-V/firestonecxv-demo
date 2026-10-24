import json

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.ai_analysis import AnalysisRateLimiter
from app.main import client_ip_for_limit, create_app


def install_mock_provider(monkeypatch, handler):
    async def dispatch(request):
        return await handler(request)

    transport = httpx.MockTransport(dispatch)
    real_client = httpx.AsyncClient
    captured = {}

    def client_factory(**kwargs):
        captured.update(kwargs)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(
        "app.ai_analysis.httpx.AsyncClient",
        client_factory,
    )
    return captured


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_VERIFICATION_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_REQUIRE_VERIFICATION_TOKEN", raising=False)
    return TestClient(create_app(str(tmp_path / "ai-demo.sqlite3")))


def configure_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://provider.example/compatible-mode/v1")
    monkeypatch.setenv("OPENAI_MODEL", "qwen3.8-flash")
    monkeypatch.delenv("DEMO_VERIFICATION_TOKEN", raising=False)


def test_ai_analysis_returns_structured_explanation_without_changing_profile(client, monkeypatch):
    configure_provider(monkeypatch)
    original_profile = client.get("/api/v1/enterprises/e01/chain-profile").json()
    completion = {
        "summary": "现有画像显示该企业处于演示评分状态。",
        "findings": ["该结论来自合成资料。"],
        "suggested_actions": ["人工核验来源材料。"],
        "limitations": ["数据不代表真实企业。"],
    }

    async def handler(request):
        assert request.url.path == "/compatible-mode/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "qwen3.8-flash"
        assert body["max_tokens"] == 800
        assert "chain of thought" in body["messages"][0]["content"]
        assert json.loads(body["messages"][1]["content"])["decision_status"] == "scored"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(completion, ensure_ascii=False)}}]})

    client_options = install_mock_provider(monkeypatch, handler)
    response = client.post("/api/v1/enterprises/e01/ai-analysis")

    assert response.status_code == 200
    result = response.json()
    assert result["summary"] == completion["summary"]
    assert result["findings"] == completion["findings"]
    assert result["suggested_actions"] == completion["suggested_actions"]
    assert result["limitations"] == completion["limitations"]
    assert result["model"] == "qwen3.8-flash"
    assert result["generated_at"]
    assert result["data_mode"] == "synthetic"
    assert result["decision_status"] == original_profile["decision_status"]
    assert client.get("/api/v1/enterprises/e01/chain-profile").json() == original_profile
    assert client_options["timeout"].read == 90.0


def test_ai_analysis_requires_provider_configuration(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("DEMO_VERIFICATION_TOKEN", raising=False)

    response = client.post("/api/v1/enterprises/e01/ai-analysis")

    assert response.status_code == 503
    assert response.json()["detail"] == "AI analysis is not configured"


@pytest.mark.parametrize("failure", ["provider", "malformed"])
def test_ai_analysis_sanitizes_provider_and_payload_failures(client, monkeypatch, failure):
    configure_provider(monkeypatch)

    async def handler(_request):
        if failure == "provider":
            return httpx.Response(500, text="provider secret details")
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    install_mock_provider(monkeypatch, handler)
    response = client.post("/api/v1/enterprises/e01/ai-analysis")

    assert response.status_code == 502
    assert response.json()["detail"] == "AI analysis provider returned an invalid response"
    assert "provider secret" not in response.text


def test_verification_token_protects_writes_but_not_ai(client, monkeypatch):
    monkeypatch.setenv("DEMO_VERIFICATION_TOKEN", "test-verification-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    profile = client.get("/api/v1/enterprises/e02/chain-profile").json()
    body = {"position_id": profile["where"]["positions"][0]["position_id"],
            "action": "confirm", "operator": "demo-reviewer", "idempotency_key": "auth-check"}

    assert client.post("/api/v1/verifications", json=body).status_code == 401
    assert client.post("/api/v1/enterprises/e01/ai-analysis",
                       headers={"Authorization": "Bearer test-verification-token"}).status_code == 503
    verified = client.post("/api/v1/verifications", json=body,
                           headers={"Authorization": "Bearer test-verification-token"})
    assert verified.status_code == 200


def test_ai_rate_limiter_enforces_per_ip_window():
    limiter = AnalysisRateLimiter(limit=2, window_seconds=60)

    assert limiter.allow("127.0.0.1", now=10)
    assert limiter.allow("127.0.0.1", now=11)
    assert not limiter.allow("127.0.0.1", now=12)
    assert limiter.allow("192.0.2.1", now=12)
    assert limiter.allow("127.0.0.1", now=70)


def test_ai_rate_limiter_bounds_client_state():
    limiter = AnalysisRateLimiter(limit=2, window_seconds=60, max_clients=2)

    assert limiter.allow("198.51.100.1", now=10)
    assert limiter.allow("198.51.100.2", now=10)
    assert limiter.allow("198.51.100.3", now=10)
    assert list(limiter.requests) == ["198.51.100.2", "198.51.100.3"]


def test_public_ai_endpoint_has_global_rate_limit(client, monkeypatch):
    configure_provider(monkeypatch)
    completion = {
        "summary": "仅基于演示画像生成。",
        "findings": [],
        "suggested_actions": [],
        "limitations": ["数据均为合成数据。"],
    }

    async def handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(completion, ensure_ascii=False)}}]})

    install_mock_provider(monkeypatch, handler)
    for index in range(30):
        response = client.post("/api/v1/enterprises/e01/ai-analysis",
                               headers={"X-Real-IP": f"198.51.100.{index + 1}"})
        assert response.status_code == 200

    limited = client.post("/api/v1/enterprises/e01/ai-analysis",
                          headers={"X-Real-IP": "203.0.113.1"})
    assert limited.status_code == 429


def make_request(headers, client_ip):
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "server": ("testserver", 80),
        "client": (client_ip, 1234),
        "root_path": "",
    })


def test_rate_limit_uses_validated_nginx_real_ip_and_ignores_forwarded_for():
    proxied = make_request({"X-Real-IP": "198.51.100.27", "X-Forwarded-For": "203.0.113.9"}, "172.20.0.4")
    invalid = make_request({"X-Real-IP": "spoofed", "X-Forwarded-For": "203.0.113.9"}, "172.20.0.4")

    assert client_ip_for_limit(proxied) == "198.51.100.27"
    assert client_ip_for_limit(invalid) == "172.20.0.4"

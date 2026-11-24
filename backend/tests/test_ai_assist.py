import json

import pytest
from app.main import app, rate, store
from app.services import ai_assist
from fastapi.testclient import TestClient


class FakeProvider:
    def __init__(self, status=200, content='{"type":"duration","rationale":"Elapsed durations."}'):
        self.status = status
        self.content = content
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        status = self.status
        content = self.content

        class Response:
            status_code = status

            def json(self):
                return {"choices": [{"message": {"content": content}}]}

        return Response()


class TimeoutProvider:
    def post(self, url, **kwargs):
        raise ai_assist.httpx.ConnectTimeout("timed out")


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    rate.clear()
    return TestClient(app)


def upload(client, rows=None):
    rows = rows or "Elapsed,City\nPT45M,Cairo\n1 day 3 hours,Giza\n"
    response = client.post(
        "/api/files/upload",
        files={"file": ("assist.csv", rows.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["file_id"]


def request_body(file_id, **overrides):
    body = {
        "file_id": file_id,
        "column": "Elapsed",
        "provider": "groq",
        "key": "gsk-test-key-123456",
        "consent": True,
    }
    body.update(overrides)
    return body


def test_assistant_requires_consent(client):
    file_id = upload(client)
    response = client.post("/api/assist", json=request_body(file_id, consent=False))
    assert response.status_code == 422
    assert "may be sent" in response.json()["detail"]


def test_assistant_can_be_disabled_server_side(client, monkeypatch):
    monkeypatch.setenv("AI_ASSIST_ENABLED", "false")
    file_id = upload(client)
    response = client.post("/api/assist", json=request_body(file_id))
    assert response.status_code == 403


def test_suggest_type_returns_validated_suggestion(client, monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(ai_assist.httpx, "post", fake.post)
    file_id = upload(client)
    response = client.post("/api/assist", json=request_body(file_id))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "suggest_type"
    assert payload["suggestion"]["type"] == "duration"
    assert payload["suggestion"]["rationale"]
    url, kwargs = fake.calls[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer gsk-test-key-123456"
    # The key is used but never echoed back to the browser.
    assert "gsk-test-key-123456" not in response.text


def test_unsupported_provider_type_is_rejected(client, monkeypatch):
    fake = FakeProvider(content='{"type":"magic","rationale":"No."}')
    monkeypatch.setattr(ai_assist.httpx, "post", fake.post)
    file_id = upload(client)
    response = client.post("/api/assist", json=request_body(file_id))
    assert response.status_code == 502
    assert "does not support" in response.json()["detail"]


def test_provider_key_rejection_is_reported(client, monkeypatch):
    monkeypatch.setattr(ai_assist.httpx, "post", FakeProvider(status=401).post)
    file_id = upload(client)
    response = client.post("/api/assist", json=request_body(file_id))
    assert response.status_code == 422
    assert "rejected this key" in response.json()["detail"]


def test_provider_timeout_is_reported(client, monkeypatch):
    monkeypatch.setattr(ai_assist.httpx, "post", TimeoutProvider().post)
    file_id = upload(client)
    response = client.post("/api/assist", json=request_body(file_id))
    assert response.status_code == 504


def test_explain_mode_returns_plain_text(client, monkeypatch):
    fake = FakeProvider(content="This column records how long each task took.")
    monkeypatch.setattr(ai_assist.httpx, "post", fake.post)
    file_id = upload(client)
    response = client.post(
        "/api/assist",
        json=request_body(
            file_id, mode="explain", message="This value looks like a time of day."
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["explanation"].startswith("This column records")


def test_explain_requires_a_finding(client, monkeypatch):
    monkeypatch.setattr(ai_assist.httpx, "post", FakeProvider().post)
    file_id = upload(client)
    response = client.post(
        "/api/assist", json=request_body(file_id, mode="explain", message="   ")
    )
    assert response.status_code == 422


def test_samples_are_bounded(client, monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(ai_assist.httpx, "post", fake.post)
    rows = "Elapsed\n" + "\n".join(f"value-{number}" for number in range(40)) + "\n"
    file_id = upload(client, rows)
    response = client.post("/api/assist", json=request_body(file_id))
    assert response.status_code == 200, response.text
    prompt = fake.calls[0][1]["json"]["messages"][1]["content"]
    samples = json.loads(prompt.split("Sample values: ", 1)[1].split("\n", 1)[0])
    assert len(samples) == 12
    assert all(len(value) <= 120 for value in samples)


def test_assistant_requires_ownership(client):
    file_id = upload(client)
    outsider = TestClient(app)
    response = outsider.post("/api/assist", json=request_body(file_id))
    assert response.status_code == 404


def test_unknown_column_is_rejected(client, monkeypatch):
    monkeypatch.setattr(ai_assist.httpx, "post", FakeProvider().post)
    file_id = upload(client)
    response = client.post("/api/assist", json=request_body(file_id, column="Missing"))
    assert response.status_code == 422
    assert "Unknown column" in response.json()["detail"]

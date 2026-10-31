import base64
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, rate, store
from app.services import identity


def token(subject, expires=None):
    payload = base64.urlsafe_b64encode(json.dumps({"sub": subject, "exp": expires or time.time() + 3600}).encode()).decode().rstrip("=")
    return "header." + payload + ".signature"


@pytest.fixture
def auth(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    monkeypatch.setenv("USAGE_DB_PATH", str(tmp_path / "usage.sqlite3"))
    monkeypatch.setattr(store, "root", tmp_path)
    identity.cache.clear()
    rate.clear()
    tokens = {token("owner"): {"id": "owner", "email": "owner@example.com", "email_confirmed_at": "2026-10-14"}, token("visitor"): {"id": "visitor", "email": "visitor@example.com", "email_confirmed_at": "2026-10-14"}}
    def provider(url, headers, **kwargs):
        assert url == "https://test.supabase.co/auth/v1/user"
        supplied = headers["Authorization"].removeprefix("Bearer ")
        return httpx.Response(200, json=tokens[supplied]) if supplied in tokens else httpx.Response(401, json={"message": "Invalid JWT"})
    monkeypatch.setattr(identity.httpx, "get", provider)
    return tokens


def test_authentication_gate_and_invalid_tokens(auth):
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/config").json()["enabled"] is True
    assert client.post("/api/files/upload", files={"file": ("x.csv", b"A\nx\n")}).status_code == 401
    assert client.post("/api/auth/session", json={"access_token": "forged"}).status_code == 401
    assert client.get("/api/admin/usage").status_code == 401


def test_verified_accounts_isolated_and_usage_contains_only_metadata(auth):
    owner_token, visitor_token = list(auth)
    owner = TestClient(app)
    response = owner.post("/api/auth/session", json={"access_token": owner_token})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json() == {"email": "owner@example.com", "admin": True}
    owner.post("/api/auth/sign-in-event")
    uploaded = owner.post("/api/files/upload", files={"file": ("private-name.csv", b"Name,Email\n Alice ,bad-email\n")})
    assert uploaded.status_code == 200
    fid = uploaded.json()["file_id"]
    other = TestClient(app)
    other.cookies.set("dataneat_session", owner.cookies.get("dataneat_session"))
    other.post("/api/auth/session", json={"access_token": visitor_token})
    assert other.get(f"/api/files/{fid}/preview").status_code == 404
    assert other.get("/api/admin/usage").status_code == 403
    owner.post(f"/api/files/{fid}/editor/start")
    fix = {"revision": 0, "column": "Email", "row_index": 0, "action": "replace", "value": "private-value@example.com"}
    assert owner.post(f"/api/files/{fid}/editor/fix", json=fix).status_code == 200
    fix["confirmed"] = True
    assert owner.post(f"/api/files/{fid}/editor/fix", json=fix).status_code == 200
    owner.get(f"/api/files/{fid}/editor/download?format=csv")
    overview = owner.get("/api/admin/usage")
    assert overview.status_code == 200
    assert overview.json()["totals"]["upload"] == 1
    assert overview.json()["totals"]["editor_fix"] == 1
    assert overview.json()["totals"]["download"] == 1
    assert "private-name.csv" not in overview.text
    assert "private-value@example.com" not in overview.text
    assert "bad-email" not in overview.text
    owner.post("/api/auth/logout")
    assert owner.get(f"/api/files/{fid}/preview").status_code == 401


def test_unverified_and_expired_accounts_rejected(auth):
    unverified = token("unverified")
    auth[unverified] = {"id": "unverified", "email": "u@example.com"}
    expired = token("expired", time.time() - 60)
    auth[expired] = {"id": "expired", "email": "e@example.com", "email_confirmed_at": "2026-10-14"}
    client = TestClient(app)
    assert client.post("/api/auth/session", json={"access_token": unverified}).status_code == 401
    assert client.post("/api/auth/session", json={"access_token": expired}).status_code == 401


def test_secret_key_never_exposed_and_partial_config_fails_closed(auth, monkeypatch):
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_secret_should_never_be_public")
    client = TestClient(app)
    config = client.get("/api/auth/config")
    assert "sb_secret" not in config.text
    assert config.json()["enabled"] is True
    assert client.get("/api/auth/me").status_code == 503


def test_usage_records_expire(auth):
    user = {"id": "past", "email": "past@example.com"}
    identity.record(user, "upload")
    with identity.database() as connection:
        connection.execute("UPDATE users SET last_seen = ?", (time.time() - 91 * 86400,))
        connection.execute("UPDATE events SET occurred_at = ?", (time.time() - 91 * 86400,))
    assert identity.overview()["users"] == []
    assert identity.overview()["totals"] == {}

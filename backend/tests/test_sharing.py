import time

import pytest
from app.main import app, rate, store
from app.services import sharing
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    rate.clear()
    return TestClient(app)


def upload(client):
    data = b"ID,City,Amount\n001, Cairo ,10\n002,cairo,20\n"
    response = client.post(
        "/api/files/upload", files={"file": ("share.csv", data, "text/csv")}
    )
    assert response.status_code == 200, response.text
    return response.json()["file_id"]


def test_share_link_is_read_only_and_revocable(client):
    file_id = upload(client)
    assert client.get(f"/api/files/{file_id}/share").json() == {"active": False}
    created = client.post(f"/api/files/{file_id}/share").json()
    token = created["token"]
    viewer = TestClient(app)
    view = viewer.get(f"/api/share/{token}")
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["filename"] == "share.csv"
    assert body["read_only"] is True
    assert body["rows"] == 2
    assert body["preview"]["total_rows"] == 2
    assert body["preview"]["columns"] == ["ID", "City", "Amount"]
    assert body["file_id"] == file_id
    report = viewer.get(f"/api/share/{token}/report")
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    # The token is never a session: editing routes remain inaccessible to it.
    assert (
        viewer.get(f"/api/files/{file_id}/editor?page=1").status_code == 404
    )
    status = client.get(f"/api/files/{file_id}/share").json()
    assert status["active"] is True
    assert status["expires_at"] > status["created_at"]
    assert client.delete(f"/api/files/{file_id}/share").json() == {"revoked": True}
    assert viewer.get(f"/api/share/{token}").status_code == 404


def test_share_link_expires(client, monkeypatch):
    file_id = upload(client)
    token = client.post(f"/api/files/{file_id}/share?ttl_hours=1").json()["token"]
    viewer = TestClient(app)
    assert viewer.get(f"/api/share/{token}").status_code == 200
    real_time = time.time
    monkeypatch.setattr(sharing.time, "time", lambda: real_time() + 2 * 3600)
    assert viewer.get(f"/api/share/{token}").status_code == 404


def test_tampered_and_transplanted_tokens_fail(client):
    file_id = upload(client)
    token = client.post(f"/api/files/{file_id}/share").json()["token"]
    other = upload(client)
    other_token = client.post(f"/api/files/{other}/share").json()["token"]
    viewer = TestClient(app)
    assert viewer.get(f"/api/share/{token}tampered").status_code == 404
    raw, signature = token.split(".")
    transplanted = f"{other_token.split('.')[0]}.{signature}"
    assert viewer.get(f"/api/share/{transplanted}").status_code == 404
    assert viewer.get(f"/api/share/{raw}.{other_token.split('.')[1]}").status_code == 404


def test_sharing_requires_ownership(client):
    file_id = upload(client)
    outsider = TestClient(app)
    assert outsider.post(f"/api/files/{file_id}/share").status_code == 404
    assert outsider.get(f"/api/files/{file_id}/share").status_code == 404
    assert outsider.delete(f"/api/files/{file_id}/share").status_code == 404


def test_deleted_file_invalidates_link(client):
    file_id = upload(client)
    token = client.post(f"/api/files/{file_id}/share").json()["token"]
    assert client.delete(f"/api/files/{file_id}").status_code == 200
    assert TestClient(app).get(f"/api/share/{token}").status_code == 404


def test_share_key_is_private_to_storage(client):
    file_id = upload(client)
    client.post(f"/api/files/{file_id}/share")
    key = store.root / ".share-key"
    assert key.exists()
    assert len(key.read_bytes()) >= 32

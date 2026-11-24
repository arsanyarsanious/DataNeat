import time

from fastapi.testclient import TestClient

import app.main as main
from app.main import app


def _csv(rows=80):
    lines = ["ID,Name,Salary"]
    lines += [f"{index},Name {index},5000" for index in range(rows)]
    return ("\n".join(lines) + "\n").encode()


def test_large_upload_is_analysis_pending_then_ready(monkeypatch):
    monkeypatch.setattr(main, "ANALYSIS_SYNC_CELLS", 0)
    client = TestClient(app)
    response = client.post(
        "/api/files/upload", files={"file": ("large.csv", _csv(), "text/csv")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_pending"] is True
    assert body["profile"] is None and body["plan"] is None

    analysis = None
    for _ in range(10):
        analysis = client.get(f"/api/files/{body['file_id']}/analysis")
        if analysis.status_code == 200:
            break
        assert analysis.status_code == 202
        time.sleep(0.05)
    assert analysis is not None and analysis.status_code == 200
    result = analysis.json()
    assert result["status"] == "ready"
    assert result["profile"]["columns"]
    assert result["plan"]
    client.delete(f"/api/files/{body['file_id']}?only_temporary=true")


def test_multipart_upload_above_one_megabyte_is_accepted(monkeypatch):
    monkeypatch.setattr(main, "ANALYSIS_SYNC_CELLS", 40000)
    client = TestClient(app)
    lines = ["Comment"] + [("x" * 120) for _ in range(10000)]
    data = ("\n".join(lines) + "\n").encode()
    assert len(data) > 1024 * 1024
    response = client.post(
        "/api/files/upload", files={"file": ("large-text.csv", data, "text/csv")}
    )
    assert response.status_code == 200, response.text
    client.delete(f"/api/files/{response.json()['file_id']}?only_temporary=true")


def test_analysis_poll_reports_pending_when_work_is_queued(monkeypatch):
    monkeypatch.setattr(main, "ANALYSIS_SYNC_CELLS", 0)
    monkeypatch.setattr(main, "analyze_file", lambda *args, **kwargs: None)
    client = TestClient(app)
    response = client.post(
        "/api/files/upload", files={"file": ("queued.csv", _csv(), "text/csv")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_pending"] is True
    pending = client.get(f"/api/files/{body['file_id']}/analysis")
    assert pending.status_code == 202
    assert pending.json()["status"] == "pending"
    client.delete(f"/api/files/{body['file_id']}?only_temporary=true")

import pytest
from app.main import app, rate, store
from fastapi.testclient import TestClient
import app.main as main


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    rate.clear()
    return TestClient(app)


def test_analysis_budget_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_WORKFLOW_CELLS", 10)
    data = b"A,B,C\n1,2,3\n4,5,6\n7,8,9\n10,11,12\n"
    response = client.post(
        "/api/files/upload", files={"file": ("budget.csv", data, "text/csv")}
    )
    assert response.status_code == 413
    assert "budget" in response.json()["detail"]


def test_analysis_budget_disabled_by_default(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_WORKFLOW_CELLS", 0)
    data = b"A,B,C\n1,2,3\n4,5,6\n"
    response = client.post(
        "/api/files/upload", files={"file": ("small.csv", data, "text/csv")}
    )
    assert response.status_code == 200, response.text


def test_storage_budget_rejects_when_full(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_STORAGE_MB", 1)
    data = b"A\n" + b"x" * (1200 * 1024) + b"\n"
    response = client.post(
        "/api/files/upload", files={"file": ("large.csv", data, "text/csv")}
    )
    assert response.status_code == 507
    assert "storage" in response.json()["detail"].lower()


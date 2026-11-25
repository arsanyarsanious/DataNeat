import io

from fastapi.testclient import TestClient

from app.main import app


def _csv():
    return (
        "Customer_ID,Name,Phone,Salary,Active,Birth_Date\n"
        "1, Cairo ,+201001234567,5000,Yes,15/05/1995\n"
        "2,cairo,01001234567,6200,TRUE,03/07/2000\n"
        "3,Kairo,00201001234567,N/A,1,N/A\n"
        "4,Cairo,+20 100 123 4567,8200,no,05/10/1997\n"
    ).encode()


def test_addin_requires_its_launch_token_when_configured(monkeypatch):
    monkeypatch.setenv("ADDIN_TOKEN", "test-addin-token")
    client = TestClient(app)
    payload = {"csv": _csv().decode(), "highlight_cap": 100}
    assert client.post("/api/addin/analyze-json", json=payload).status_code == 401
    assert client.post(
        "/api/addin/analyze-json",
        json=payload,
        headers={"X-Addin-Token": "wrong-token"},
    ).status_code == 401
    allowed = client.post(
        "/api/addin/analyze-json",
        json=payload,
        headers={"X-Addin-Token": "test-addin-token"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["rows"] == 4
    assert client.get("/api/health").status_code == 200


def test_same_origin_tunnel_style_request_is_not_rejected_by_cors():
    client = TestClient(app)
    response = client.post(
        "/api/files/upload",
        headers={"Origin": "https://testserver"},
        files={"file": ("origin.csv", b"A\nx\n", "text/csv")},
    )
    assert response.status_code == 200, response.text


def test_addin_analyze_returns_compact_issue_map():
    client = TestClient(app)
    response = client.post(
        "/api/addin/analyze",
        files={"file": ("sheet.csv", _csv(), "text/csv")},
        data={"highlight_cap": "100"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows"] == 4
    assert body["columns_count"] == 6
    assert body["total_issue_cells"] > 0
    assert len(body["cells"]) <= 100
    assert any(column["issues"] for column in body["columns"])
    assert body["cells"][0]["kinds"]
    assert body["truncated"] is False


def test_addin_analyze_caps_highlight_cells_but_keeps_total():
    client = TestClient(app)
    response = client.post(
        "/api/addin/analyze",
        files={"file": ("sheet.csv", _csv(), "text/csv")},
        data={"highlight_cap": "1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["cells"]) == 1
    assert body["total_issue_cells"] > 1
    assert body["truncated"] is True


def test_addin_analyze_json_accepts_excel_web_snapshot():
    client = TestClient(app)
    response = client.post(
        "/api/addin/analyze-json",
        json={"csv": _csv().decode(), "highlight_cap": 100},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows"] == 4
    assert body["columns_count"] == 6
    assert body["cells"]
    assert body["total_issue_cells"] > 0


def test_addin_analyze_rejects_empty_file():
    client = TestClient(app)
    response = client.post(
        "/api/addin/analyze",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 422

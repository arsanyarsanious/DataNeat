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


def test_addin_analyze_rejects_empty_file():
    client = TestClient(app)
    response = client.post(
        "/api/addin/analyze",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 422

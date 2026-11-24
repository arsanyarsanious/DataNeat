import time

import pytest
from app.main import app, rate, store
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    rate.clear()
    return TestClient(app)


def wait(client, job_id):
    for _ in range(300):
        status = client.get(f"/api/workflow-jobs/{job_id}").json()
        if status["status"] in ("completed", "failed", "cancelled"):
            return status
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def upload(client, data):
    response = client.post(
        "/api/files/upload", files={"file": ("rates.csv", data, "text/csv")}
    )
    assert response.status_code == 200, response.text
    return response.json()


def init(client, file_id):
    response = client.post(f"/api/files/{file_id}/workflow/init")
    assert response.status_code == 200, response.text
    return response.json()


def decide(client, file_id, revision, decision):
    started = client.post(
        f"/api/files/{file_id}/workflow/jobs",
        json={"revision": revision, "operation": "decision", "decision": decision},
    )
    assert started.status_code == 202, started.text
    return wait(client, started.json()["job_id"])


def declare_scale(client, file_id, revision, scale):
    result = decide(
        client,
        file_id,
        revision,
        {"kind": "rules", "column": "Rate", "settings": {"type": "percentage", "percentage_scale": scale}},
    )
    assert result["status"] == "completed", result
    return result["result"]["revision"]


def column_issues(client, file_id, column="Rate"):
    sheet = client.get(f"/api/files/{file_id}/editor?page=1").json()
    return sheet, next(
        item for item in sheet["profile"]["columns"] if item["column_name"] == column
    )


RATES = b"Rate\n0.96\n0.84\n0.60\n"
RATES_MISSING = b"Rate,Id\n0.96,1\n0.84,2\n,3\n0.60,4\n"


def test_bare_percentage_column_is_flagged_until_scale_declared(client):
    uploaded = upload(client, RATES)
    assert uploaded["profile"]["columns"][0]["detected_type"] == "percentage"
    issues = {item["issue"]: item["count"] for item in uploaded["profile"]["columns"][0]["issues"]}
    assert issues.get("percentage_scale") == 3
    sheet = init(client, uploaded["file_id"])
    flags = [
        [flag["kind"] for flag in row[0]]
        for row in sheet["preview"]["cell_issues"]
    ]
    assert all("percentage_scale" in row for row in flags)

    revision = declare_scale(client, uploaded["file_id"], sheet["revision"], "ratio")
    sheet, column = column_issues(client, uploaded["file_id"])
    assert revision == sheet["revision"]
    assert "percentage_scale" not in {item["issue"] for item in column["issues"]}
    flags = [
        [flag["kind"] for flag in row[0]]
        for row in sheet["preview"]["cell_issues"]
    ]
    assert not any("percentage_scale" in row for row in flags)


def test_percentage_imputation_requires_declared_scale(client):
    uploaded = upload(client, RATES_MISSING)
    file_id = uploaded["file_id"]
    sheet = init(client, file_id)
    failed = decide(
        client,
        file_id,
        sheet["revision"],
        {
            "kind": "fix",
            "body": {
                "revision": sheet["revision"],
                "column": "Rate",
                "row_index": 0,
                "scope": "column",
                "action": "impute_missing_values",
                "parameters": {"method": "mean", "confirmed": True},
            },
        },
    )
    assert failed["status"] == "failed"
    assert "percentage" in failed["error"].lower()
    # Nothing was committed by the blocked fill.
    sheet = client.get(f"/api/files/{file_id}/editor?page=1").json()
    assert sheet["changes"] == []


def test_declared_ratio_scale_scales_bare_values_for_imputation(client):
    uploaded = upload(client, RATES_MISSING)
    file_id = uploaded["file_id"]
    sheet = init(client, file_id)
    revision = declare_scale(client, file_id, sheet["revision"], "ratio")
    result = decide(
        client,
        file_id,
        revision,
        {
            "kind": "fix",
            "body": {
                "revision": revision,
                "column": "Rate",
                "row_index": 0,
                "scope": "column",
                "action": "impute_missing_values",
                "parameters": {"method": "mean", "confirmed": True},
            },
        },
    )
    assert result["status"] == "completed", result
    sheet = client.get(f"/api/files/{file_id}/editor?page=1").json()
    filled = sheet["preview"]["rows"][2][0]
    assert float(filled) == pytest.approx(80.0)


def test_declared_points_scale_keeps_bare_values_as_points(client):
    uploaded = upload(client, RATES_MISSING)
    file_id = uploaded["file_id"]
    sheet = init(client, file_id)
    revision = declare_scale(client, file_id, sheet["revision"], "points")
    result = decide(
        client,
        file_id,
        revision,
        {
            "kind": "fix",
            "body": {
                "revision": revision,
                "column": "Rate",
                "row_index": 0,
                "scope": "column",
                "action": "impute_missing_values",
                "parameters": {"method": "mean", "confirmed": True},
            },
        },
    )
    assert result["status"] == "completed", result
    sheet = client.get(f"/api/files/{file_id}/editor?page=1").json()
    filled = sheet["preview"]["rows"][2][0]
    assert float(filled) == pytest.approx(0.8)


def test_automatic_cleaning_skips_undeclared_percentage_scale(client):
    uploaded = upload(client, b"Rate,Name\n0.96,a\n0.84,b\n0.60,c\n")
    file_id = uploaded["file_id"]
    sheet = init(client, file_id)
    started = client.post(
        f"/api/files/{file_id}/workflow/jobs",
        json={
            "revision": sheet["revision"],
            "operation": "automatic",
            "answers": {
                "trim": True,
                "boolean": "preserve",
                "capitalization": "preserve",
                "dates": "preserve",
                "date_output": "YYYY-MM-DD",
                "missing": "preserve",
                "duplicates": "preserve",
                "exceptions": {},
            },
        },
    )
    assert started.status_code == 202, started.text
    result = wait(client, started.json()["job_id"])
    assert result["status"] == "completed", result
    assert any("percentage" in note for note in result["result"]["skipped"])
    assert result["result"]["operations"] == []


def test_percentage_rule_bounds_require_declared_scale():
    from app.core.workflow import number_for

    with pytest.raises(ValueError, match="Declare whether bare percentage"):
        number_for("0.96", {"type": "percentage"})
    assert float(number_for("0.96", {"type": "percentage", "percentage_scale": "ratio"})) == 96
    assert float(number_for("0.96", {"type": "percentage", "percentage_scale": "points"})) == 0.96

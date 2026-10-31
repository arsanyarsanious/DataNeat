"""Legacy endpoints must obey the same column readiness policy as workflows."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app, rate, store


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    store.access.clear()
    rate.clear()
    return TestClient(app)


def upload(client, content=None):
    content = content or b"ID,Amount,Email\n1,10,bad\n2,20,a@example.com\n3,,b@example.com\n4,40,c@example.com\n5,50,d@example.com\n6,60,e@example.com\n7,oops,f@example.com\n"
    response = client.post("/api/files/upload", files={"file": ("legacy.csv", content, "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()["file_id"]


def fill(method="mean", **parameters):
    return {"operation": "impute_missing_values", "column": "Amount", "enabled": True,
            "parameters": {"method": method, "confirmed": True, **parameters}}


def job_result(client, job_id):
    for _ in range(150):
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in ("completed", "failed", "cancelled"):
            return result
        time.sleep(0.01)
    pytest.fail("Legacy cleaning job did not finish")


@pytest.mark.parametrize("method,settings", [("mean", {}), ("median", {}), ("mode", {}), ("constant", {"value": "0"})])
def test_legacy_preview_blocks_every_imputation_method_until_other_issues_resolved(client, method, settings):
    fid = upload(client)
    response = client.post(f"/api/files/{fid}/preview-cleaning", json={"operations": [fill(method, **settings)]})
    assert response.status_code == 422, response.text
    message = response.json()["detail"]
    assert "Column 'Amount'" in message and "resolve other issues before filling" in message
    assert "B8 (spreadsheet row 8)" in message
    assert client.get(f"/api/files/{fid}/preview").json()["rows"][2][1] == ""


@pytest.mark.parametrize("endpoint", ["clean", "preview-cleaning?background=true"])
def test_background_legacy_endpoints_fail_atomically_with_readable_blocker(client, endpoint):
    fid = upload(client)
    response = client.post(f"/api/files/{fid}/{endpoint}", json={"operations": [fill("constant", value="0")]})
    assert response.status_code in (200, 202), response.text
    result = job_result(client, response.json()["job_id"])
    assert result["status"] == "failed", result
    assert "Column 'Amount'" in result["error"] and "B8" in result["error"]
    assert client.get(f"/api/files/{fid}/preview").json()["rows"][2][1] == ""


def test_legacy_plan_can_resolve_target_issues_before_imputation_and_keeps_legacy_order(client):
    fid = upload(client)
    # Submitted order is intentionally reversed. Legacy dependencies still run first.
    operations = [fill(), {"operation": "normalize_missing_values", "column": "Amount", "enabled": True,
                           "parameters": {"markers": ["oops"]}}]
    response = client.post(f"/api/files/{fid}/preview-cleaning", json={"operations": operations})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["after"]["rows"][2][1] == 36
    assert result["after"]["rows"][6][1] == 36
    assert [operation["operation"] for operation in result["operations"]] == ["normalize_missing_values", "impute_missing_values"]
    # An unrelated invalid email does not block the clean Amount column.
    assert result["after"]["rows"][0][2] == "bad"
    queued = client.post(f"/api/files/{fid}/clean", json={"operations": operations})
    done = job_result(client, queued.json()["job_id"])
    assert done["status"] == "completed", done


def test_legacy_gate_retains_explicit_date_output_interpretation_in_same_plan(client):
    fid = upload(client, b"ID,Event_Date\n1,01/02/2024\n2,03/02/2024\n3,\n4,05/02/2024\n")
    operations = [
        {"operation": "normalize_dates", "column": "Event_Date", "enabled": True,
         "parameters": {"interpretation": "day_first", "output_format": "DD/MM/YYYY"}},
        {"operation": "impute_missing_values", "column": "Event_Date", "enabled": True,
         "parameters": {"method": "median", "confirmed": True}},
    ]
    response = client.post(f"/api/files/{fid}/preview-cleaning", json={"operations": operations})
    assert response.status_code == 200, response.text
    assert response.json()["after"]["rows"][2][1] == "03/02/2024"


@pytest.mark.parametrize("action,parameters,value", [
    ("impute_missing_values", {"method": "mode"}, None),
    ("impute_missing_values", {"method": "constant", "value": "0"}, None),
    ("replace", {}, "0"),
])
@pytest.mark.parametrize("confirmed", [False, True])
def test_nonworkflow_editor_blocks_imputation_and_manual_blank_fill(client, action, parameters, value, confirmed):
    fid = upload(client)
    assert client.post(f"/api/files/{fid}/editor/start").status_code == 200
    body = {"revision": 0, "column": "Amount", "row_index": 2, "scope": "cell",
            "action": action, "parameters": parameters, "value": value, "confirmed": confirmed}
    response = client.post(f"/api/files/{fid}/editor/fix", json=body)
    assert response.status_code == 422, response.text
    assert "resolve other issues before filling" in response.json()["detail"]
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["revision"] == 0 and current["preview"]["rows"][2][1] is None


def test_nonworkflow_clear_then_fill_becomes_allowed_without_workflow_migration(client):
    fid = upload(client)
    client.post(f"/api/files/{fid}/editor/start")
    clear = {"revision": 0, "column": "Amount", "row_index": 6, "scope": "cell",
             "action": "replace", "value": None, "confirmed": True}
    response = client.post(f"/api/files/{fid}/editor/fix", json=clear)
    assert response.status_code == 200, response.text
    filled = client.post(f"/api/files/{fid}/editor/fix", json={**clear, "revision": 1, "row_index": 2,
                          "action": "impute_missing_values", "parameters": {"method": "mean"}})
    assert filled.status_code == 200, filled.text
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["revision"] == 2 and current["preview"]["rows"][2][1] == 36
    assert not store.get(fid, client.cookies.get("dataneat_session")).get("workflow_version")


def test_preserve_missing_values_remains_available_even_when_other_issues_exist(client):
    fid = upload(client)
    result = client.post(f"/api/files/{fid}/preview-cleaning", json={"operations": [fill("preserve")]})
    assert result.status_code == 200, result.text
    assert result.json()["after"]["rows"][2][1] == ""

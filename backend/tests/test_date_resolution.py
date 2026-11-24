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
        if status["status"] == "completed":
            return status["result"]
        if status["status"] == "failed":
            raise AssertionError(status.get("error", "job failed"))
        time.sleep(0.02)
    raise AssertionError("job did not complete")


def upload(client, data):
    response = client.post(
        "/api/files/upload", files={"file": ("dates.csv", data, "text/csv")}
    )
    assert response.status_code == 200, response.text
    return response.json()


def answers(dates="day_first", output="YYYY-MM-DD"):
    return {
        "trim": False,
        "boolean": "preserve",
        "capitalization": "preserve",
        "dates": dates,
        "date_output": output,
        "missing": "preserve",
        "duplicates": "preserve",
        "exceptions": {},
    }


def automatic(client, file_id, revision, **overrides):
    body = answers(**overrides)
    started = client.post(
        f"/api/files/{file_id}/workflow/jobs",
        json={"revision": revision, "operation": "automatic", "answers": body},
    )
    assert started.status_code == 202, started.text
    return wait(client, started.json()["job_id"])


def values(client, file_id):
    sheet = client.get(f"/api/files/{file_id}/editor?page=1").json()
    return [row[0] for row in sheet["preview"]["rows"]], sheet


AMBIGUOUS = b"Birth_Date\n05/10/2025\n01/02/2024\n15/05/1995\n"


def test_automatic_day_first_resolves_ambiguous_dates(client):
    uploaded = upload(client, AMBIGUOUS)
    file_id = uploaded["file_id"]
    assert uploaded["profile"]["columns"][0]["detected_type"] == "date"
    init = client.post(f"/api/files/{file_id}/workflow/init").json()
    result = automatic(client, file_id, init["revision"], dates="day_first")
    operations = [(item["action"], item["changed_cells"]) for item in result["operations"]]
    assert operations == [("normalize_dates", 3)]
    after, sheet = values(client, file_id)
    assert after == ["2025-10-05", "2024-02-01", "1995-05-15"]
    kinds = [
        flag["kind"]
        for row in sheet["preview"]["cell_issues"]
        for cell in row
        for flag in cell
    ]
    assert "ambiguous_date" not in kinds


def test_automatic_month_first_resolves_ambiguous_dates(client):
    uploaded = upload(client, AMBIGUOUS)
    file_id = uploaded["file_id"]
    init = client.post(f"/api/files/{file_id}/workflow/init").json()
    automatic(client, file_id, init["revision"], dates="month_first")
    after, _ = values(client, file_id)
    assert after == ["2025-05-10", "2024-01-02", "1995-05-15"]


def test_automatic_preserve_leaves_ambiguous_dates(client):
    uploaded = upload(client, AMBIGUOUS)
    file_id = uploaded["file_id"]
    init = client.post(f"/api/files/{file_id}/workflow/init").json()
    result = automatic(client, file_id, init["revision"], dates="preserve")
    assert result["operations"] == []
    after, _ = values(client, file_id)
    assert after == ["05/10/2025", "01/02/2024", "15/05/1995"]


def test_automatic_unambiguous_only_keeps_ambiguous_dates(client):
    uploaded = upload(client, AMBIGUOUS)
    file_id = uploaded["file_id"]
    init = client.post(f"/api/files/{file_id}/workflow/init").json()
    result = automatic(client, file_id, init["revision"], dates="unambiguous")
    assert [(item["action"], item["changed_cells"]) for item in result["operations"]] == [
        ("normalize_dates", 1)
    ]
    after, _ = values(client, file_id)
    assert after == ["05/10/2025", "01/02/2024", "1995-05-15"]


def manual_normalize(client, file_id, revision, interpretation, output="YYYY-MM-DD"):
    started = client.post(
        f"/api/files/{file_id}/workflow/jobs",
        json={
            "revision": revision,
            "operation": "decision",
            "decision": {
                "kind": "fix",
                "body": {
                    "revision": revision,
                    "column": "Birth_Date",
                    "row_index": 0,
                    "scope": "column",
                    "action": "normalize_dates",
                    "parameters": {
                        "interpretation": interpretation,
                        "include_time": False,
                        "output_format": output,
                    },
                },
            },
        },
    )
    assert started.status_code == 202, started.text
    return wait(client, started.json()["job_id"])


def test_manual_day_first_resolves_ambiguous_dates(client):
    uploaded = upload(client, AMBIGUOUS)
    file_id = uploaded["file_id"]
    init = client.post(f"/api/files/{file_id}/workflow/init").json()
    result = manual_normalize(client, file_id, init["revision"], "day_first")
    assert result["proposal"]["changed_cells"] == 3
    after, _ = values(client, file_id)
    assert after == ["2025-10-05", "2024-02-01", "1995-05-15"]


def test_manual_preserve_only_standardizes_unambiguous_dates(client):
    uploaded = upload(client, AMBIGUOUS)
    file_id = uploaded["file_id"]
    init = client.post(f"/api/files/{file_id}/workflow/init").json()
    manual_normalize(client, file_id, init["revision"], "preserve")
    after, _ = values(client, file_id)
    assert after == ["05/10/2025", "01/02/2024", "1995-05-15"]


def test_declared_date_column_is_normalized_by_automatic_cleaning(client):
    uploaded = upload(client, b"Notes\n05/10/2025\nTBD\npending\nreview\n")
    file_id = uploaded["file_id"]
    assert uploaded["profile"]["columns"][0]["detected_type"] not in ("date", "datetime")
    init = client.post(f"/api/files/{file_id}/workflow/init").json()
    declared = client.post(
        f"/api/files/{file_id}/workflow/jobs",
        json={
            "revision": init["revision"],
            "operation": "decision",
            "decision": {"kind": "rules", "column": "Notes", "settings": {"type": "date"}},
        },
    )
    assert declared.status_code == 202, declared.text
    changed = wait(client, declared.json()["job_id"])
    result = automatic(client, file_id, changed["revision"], dates="day_first")
    operations = [(item["column"], item["action"], item["changed_cells"]) for item in result["operations"]]
    assert operations == [("Notes", "normalize_dates", 1)]
    after, _ = values(client, file_id)
    assert after == ["2025-10-05", "TBD", "pending", "review"]

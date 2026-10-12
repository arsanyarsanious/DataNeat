import io
import time

import pytest
from app.main import app, rate, store
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    rate.clear()
    # Avoid shutting down the shared executor between tests.
    return TestClient(app)


def upload(
    client,
    data=b"ID,City,Birth_Date,Notes\n001, Cairo ,05/10/2025,=1+1\n002,cairo,15/05/2025,normal\n",
):
    response = client.post(
        "/api/files/upload", files={"file": ("customers.csv", data, "text/csv")}
    )
    assert response.status_code == 200, response.text
    return response.json()


def wait_job(client, job):
    for _ in range(100):
        response = client.get(f"/api/jobs/{job}").json()
        if response["status"] == "completed":
            return
        assert response["status"] != "failed", response
        time.sleep(0.02)
    pytest.fail("Job did not complete")


def test_real_workflow_and_authorization(client):
    uploaded = upload(client)
    fid = uploaded["file_id"]
    assert client.get(f"/api/files/{fid}/profile").json()["rows"] == 2
    assert client.get(f"/api/files/{fid}/issues").status_code == 200
    assert client.get(f"/api/files/{fid}/cleaning-plan").status_code == 200
    outsider = TestClient(app)
    assert outsider.get(f"/api/files/{fid}/preview").status_code == 404
    plan = uploaded["plan"]
    for op in plan:
        op["enabled"] = True
    body = {"operations": plan}
    trial = client.post(f"/api/files/{fid}/preview-cleaning", json=body)
    assert trial.status_code == 200, trial.text
    assert trial.json()["after"]["rows"][0][2] == "05/10/2025"
    response = client.post(f"/api/files/{fid}/clean", json=body)
    assert response.status_code == 202
    job = response.json()["job_id"]
    wait_job(client, job)
    assert outsider.get(f"/api/jobs/{job}/download").status_code == 404
    results = client.get(f"/api/jobs/{job}/results").json()
    assert results["preview"]["rows"][0][0] == "001"
    assert results["preview"]["rows"][0][1] == "Cairo"
    assert results["validation"]["unresolved_issues"] > 0
    csv = client.get(f"/api/jobs/{job}/download?format=csv")
    assert "'=1+1" in csv.text and "001" in csv.text
    excel = client.get(f"/api/jobs/{job}/download?format=xlsx")
    workbook = load_workbook(io.BytesIO(excel.content))
    assert workbook.active["A2"].value == "001"
    assert workbook.active["D2"].data_type != "f"
    assert client.get(f"/api/jobs/{job}/download?format=report").json()["validation"]
    assert client.get(f"/api/files/{fid}/preview").json()["rows"][0][1] == " Cairo "
    assert client.delete(f"/api/files/{fid}").status_code == 200
    assert client.get(f"/api/jobs/{job}").status_code == 404
    assert client.get(f"/api/files/{fid}/profile").status_code == 404


def test_excel_sheets(client):
    workbook = Workbook()
    workbook.active.title = "First"
    workbook.active.append(["ID", "Date"])
    workbook.active.append(["001", "05/10/2025"])
    other = workbook.create_sheet("Second")
    other.append(["Name", "Name"])
    other.append(["Alice", "Bob"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    response = client.post(
        "/api/files/upload",
        files={"file": ("book.xlsx", buffer.getvalue())},
        data={"sheet": "Second"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metadata"]["sheets"] == ["First", "Second"]
    assert result["preview"]["columns"] == ["Name", "Name_2"]
    assert result["preview"]["rows"] == [["Alice", "Bob"]]


def test_validation_limits_and_origin(client):
    for name, data in [
        ("bad.txt", b"abc"),
        ("empty.csv", b""),
        ("invalid.xlsx", b"not a workbook"),
    ]:
        assert (
            client.post("/api/files/upload", files={"file": (name, data)}).status_code
            == 422
        )
    assert (
        client.post(
            "/api/files/upload",
            headers={"Origin": "https://evil.example"},
            files={"file": ("x.csv", b"a\n1")},
        ).status_code
        == 403
    )
    fid = upload(client)["file_id"]
    assert client.get(f"/api/files/{fid}/preview?page=0").status_code == 422
    assert client.get("/api/files/not-a-uuid/preview").status_code == 404
    record = store.get(fid, client.cookies.get("dataneat_session"))
    record["created"] = time.time() - 86401
    store.save(record)
    assert client.get(f"/api/files/{fid}/profile").status_code == 404


def test_resource_limits_pagination_and_cleanup(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "MAX_UPLOAD", 5)
    assert (
        client.post(
            "/api/files/upload", files={"file": ("large.csv", b"a\n123456789")}
        ).status_code
        == 413
    )
    monkeypatch.setattr(main, "MAX_UPLOAD", 20 * 1024 * 1024)
    uploaded = upload(client, b"ID\n001\n002\n003\n")
    fid = uploaded["file_id"]
    paged = client.get(f"/api/files/{fid}/preview?page=2&page_size=1").json()
    assert paged["rows"] == [["002"]]
    path = store.path(fid)
    import os

    expired = time.time() - 86401
    os.utime(path, (expired, expired))
    store.purge()
    assert not path.exists()


def test_formula_headers_and_precision(client):
    result = upload(client, b'=header,Amount\n=1+1,"99999999999999999999.123456789"\n')
    fid = result["file_id"]
    ops = [
        {
            "operation": "normalize_numeric",
            "column": "Amount",
            "enabled": True,
            "parameters": {},
        }
    ]
    job = client.post(f"/api/files/{fid}/clean", json={"operations": ops}).json()[
        "job_id"
    ]
    wait_job(client, job)
    text = client.get(f"/api/jobs/{job}/download").text
    assert "'=header" in text and "'=1+1" in text
    assert "99999999999999999999.123456789" in text


def test_excel_formatted_identifier_and_encoding(client):
    workbook = Workbook()
    ws = workbook.active
    ws.append(["ID", "City"])
    ws.append([1, "Cairo"])
    ws["A2"].number_format = "000"
    buffer = io.BytesIO()
    workbook.save(buffer)
    result = client.post(
        "/api/files/upload", files={"file": ("book.xlsx", buffer.getvalue())}
    ).json()
    assert result["preview"]["rows"][0][0] == "001"
    assert result["profile"]["columns"][0]["detected_type"] == "identifier"
    result = client.post(
        "/api/files/upload",
        files={"file": ("unicode.csv", "ID,City\n001,القاهرة\n".encode("utf-16"))},
    ).json()
    assert result["preview"]["rows"][0][1] == "القاهرة"


def test_rate_limit_and_streamed_body(client):
    from collections import deque

    import app.main as main

    main.rate["testclient"] = deque([time.monotonic()] * 120)
    assert client.get("/api/health").status_code == 429
    main.rate.clear()
    import asyncio

    from app.services.limits import BodyLimitMiddleware
    from fastapi import HTTPException

    async def scenario():
        async def receive():
            return {"type": "http.request", "body": b"123456"}

        async def downstream(scope, receive, send):
            await receive()

        middleware = BodyLimitMiddleware(downstream, max_bytes=5)
        with pytest.raises(HTTPException) as exc:
            await middleware({"type": "http"}, receive, None)
        assert exc.value.status_code == 413

    asyncio.run(scenario())


def test_invalid_cleaning_parameters_are_rejected(client):
    fid = upload(client)["file_id"]
    invalid = [
        {
            "operation": "normalize_dates",
            "column": "Birth_Date",
            "parameters": {"interpretation": "guess"},
        },
        {
            "operation": "normalize_missing_values",
            "column": "City",
            "parameters": {"markers": "NA"},
        },
        {"operation": "remove_duplicates", "parameters": {"subset": "City"}},
        {"operation": "rename_column", "column": "City", "parameters": {"name": 123}},
    ]
    for operation in invalid:
        response = client.post(
            f"/api/files/{fid}/preview-cleaning",
            json={"operations": [{**operation, "enabled": True}]},
        )
        assert response.status_code == 422


def test_invalid_date_rows_are_paginated_isolated_and_correctable(client):
    result = upload(
        client,
        b"Event,Amount\n88-99-2089,$100\n31/02/2025,200 USD\n05/10/2025,300\n2025-10-05,EUR 400\n",
    )
    fid = result["file_id"]
    rows = client.get(
        f"/api/files/{fid}/invalid-dates",
        params={"column": "Event", "page_size": 1, "page": 2},
    ).json()
    assert rows["total"] == 2 and rows["rows"] == [
        {"row_index": 1, "spreadsheet_row": 3, "value": "31/02/2025"}
    ]
    outsider = TestClient(app)
    assert (
        outsider.get(f"/api/files/{fid}/invalid-dates?column=Event").status_code == 404
    )
    assert (
        client.get(f"/api/files/{fid}/invalid-dates?column=Amount").status_code == 422
    )
    dates = next(o for o in result["plan"] if o["operation"] == "resolve_invalid_dates")
    dates.update(
        enabled=True,
        parameters={"action": "manual", "replacements": {"0": "2025-10-06", "1": None}},
    )
    money = next(o for o in result["plan"] if o["operation"] == "normalize_currency")
    money.update(
        enabled=True,
        parameters={
            "currency": "USD",
            "format": "code",
            "assume_unlabelled": True,
            "symbol_aliases": ["$"],
        },
    )
    body = {"operations": [dates, money]}
    preview = client.post(f"/api/files/{fid}/preview-cleaning", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["after"]["rows"] == [
        ["2025-10-06", "USD 100"],
        [None, "USD 200"],
        ["05/10/2025", "USD 300"],
        ["2025-10-05", "EUR 400"],
    ]
    job = client.post(f"/api/files/{fid}/clean", json=body).json()["job_id"]
    wait_job(client, job)
    results = client.get(f"/api/jobs/{job}/results").json()
    assert results["validation"]["invalid_dates_resolved"] == 2
    assert (
        results["validation"]["unresolved_issues"] > 0
    )  # EUR and ambiguity still need review.
    assert client.get(f"/api/files/{fid}/preview").json()["rows"][0] == [
        "88-99-2089",
        "$100",
    ]
    for op in (
        {
            **dates,
            "parameters": {"action": "manual", "replacements": {"0": "88-99-2089"}},
        },
        {**money, "parameters": {"currency": "USD", "assume_unlabelled": "yes"}},
        {**money, "parameters": {"currency": "USD", "symbol_aliases": ["EUR"]}},
    ):
        assert (
            client.post(
                f"/api/files/{fid}/preview-cleaning", json={"operations": [op]}
            ).status_code
            == 422
        )

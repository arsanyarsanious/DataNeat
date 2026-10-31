import io

import pandas as pd
import pytest
from app.core.interactive import basic_cleanup
from app.main import app, rate, store
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook


def test_unify_text_values_across_pages_and_undo(client):
    csv = "City,Other\n" + "Cairo,keep\n" * 30 + "Kairo,keep\ncairo,keep\nAlexandria,keep\nN/A,keep\n"
    fid = client.post("/api/files/upload", files={"file": ("cities.csv", csv.encode(), "text/csv")}).json()["file_id"]
    client.post(f"/api/files/{fid}/editor/start")
    values = client.get(f"/api/files/{fid}/editor/text-values", params={"column": "City"}).json()
    assert next(item["count"] for item in values["values"] if item["value"] == "Cairo") == 30
    assert not any(item["value"] == "N/A" for item in values["values"])
    assert TestClient(app).get(f"/api/files/{fid}/editor/text-values?column=City").status_code == 404
    body = {"revision": 0, "column": "City", "row_index": 0, "scope": "values", "action": "replace", "value": "Cairo", "parameters": {"source_values": ["Cairo", "Kairo"]}}
    preview = client.post(f"/api/files/{fid}/editor/fix", json=body)
    assert preview.status_code == 200
    assert preview.json()["proposal"]["changed_cells"] == 1
    assert store.get(fid, client.cookies.get("dataneat_session"))["editor_df"].loc[30, "City"] == "Kairo"
    assert client.post(f"/api/files/{fid}/editor/fix", json={**body, "confirmed": True}).status_code == 200
    df = store.get(fid, client.cookies.get("dataneat_session"))["editor_df"]
    assert df.loc[30, "City"] == "Cairo"
    assert df.loc[31, "City"] == "cairo"
    assert df.loc[32, "City"] == "Alexandria"
    assert df.loc[33, "City"] is None
    assert set(df["Other"]) == {"keep"}
    change = store.get(fid, client.cookies.get("dataneat_session"))["editor_changes"][-1]
    assert client.post(f"/api/files/{fid}/editor/undo/{change['id']}?revision=1").status_code == 200
    assert store.get(fid, client.cookies.get("dataneat_session"))["editor_df"].loc[30, "City"] == "Kairo"
    assert client.post(f"/api/files/{fid}/editor/fix", json={**body, "revision": 2, "parameters": {"source_values": ["Cairo", "absent"]}}).status_code == 422
    assert client.post(f"/api/files/{fid}/editor/fix", json={**body, "revision": 2, "value": ""}).status_code == 422


def test_background_editor_status_and_session_isolation(client, monkeypatch):
    from concurrent.futures import Future
    from app import main

    queued = []
    future = Future()

    def submit(function, *args):
        queued.append((function, args))
        return future

    monkeypatch.setattr(main.executor, "submit", submit)
    fid = upload(client)
    response = client.post(f"/api/files/{fid}/editor/start?background=true")
    assert response.status_code == 202
    assert response.json() == {"status": "processing"}
    assert client.get(f"/api/files/{fid}/editor/status").json()["status"] == "processing"
    assert client.get(f"/api/files/{fid}/editor").status_code == 409
    assert client.post(f"/api/files/{fid}/editor/start?background=true").status_code == 202
    assert len(queued) == 1  # Duplicate requests share the same preparation.
    outsider = TestClient(app)
    assert outsider.get(f"/api/files/{fid}/editor/status").status_code == 404
    function, args = queued[0]
    function(*args)
    future.set_result(None)
    assert client.get(f"/api/files/{fid}/editor/status").json()["status"] == "ready"
    sheet = client.get(f"/api/files/{fid}/editor").json()
    assert sheet["preview"]["rows"][0][1] == "mary david"
    assert sheet["basic_log"] == []
    assert sheet["preview"]["cell_issues"][2][2][0]["kind"] == "invalid_date"
    assert client.get(f"/api/files/{fid}/preview").json()["rows"][0][1] == " mary david "


def test_deleted_upload_is_not_recreated_by_background_editor(client, monkeypatch):
    from concurrent.futures import Future
    from app import main

    queued = []
    monkeypatch.setattr(main.executor, "submit", lambda f, *a: queued.append((f, a)) or Future())
    fid = upload(client)
    client.post(f"/api/files/{fid}/editor/start?background=true")
    assert client.delete(f"/api/files/{fid}").status_code == 200
    function, args = queued[0]
    function(*args)
    assert not store.path(fid).exists()


def test_background_editor_failure_is_readable(client, monkeypatch):
    from concurrent.futures import Future
    from app import main

    future = Future()
    monkeypatch.setattr(main.executor, "submit", lambda *a: future)
    fid = upload(client)
    client.post(f"/api/files/{fid}/editor/start?background=true")
    future.set_exception(RuntimeError("internal implementation detail"))
    response = client.get(f"/api/files/{fid}/editor/status")
    assert response.status_code == 500
    assert "could not be prepared" in response.json()["detail"]
    assert "internal implementation detail" not in response.text
    client.delete(f"/api/files/{fid}")


def test_replace_matching_values_across_pages_requires_confirmation(client):
    rows = ["invalid-email" if i in (0, 30) else "valid@example.com" for i in range(35)]
    rows[2] = "INVALID-EMAIL"
    data = "Email,Notes\n" + "\n".join(f"{v},invalid-email" for v in rows)
    fid = client.post("/api/files/upload", files={"file": ("matches.csv", data.encode(), "text/csv")}).json()["file_id"]
    client.post(f"/api/files/{fid}/editor/start")
    body = {"revision": 0, "column": "Email", "row_index": 0, "scope": "matching", "action": "replace", "value": "fixed@example.com"}
    response = client.post(f"/api/files/{fid}/editor/fix", json=body)
    assert response.status_code == 200
    assert response.json()["proposal"]["changed_cells"] == 2
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"][0][0] == "invalid-email"
    body["confirmed"] = True
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    first = client.get(f"/api/files/{fid}/editor").json()["preview"]
    second = client.get(f"/api/files/{fid}/editor?page=2").json()["preview"]
    assert first["rows"][0] == ["fixed@example.com", "invalid-email"]
    assert first["rows"][2][0] == "INVALID-EMAIL"
    assert second["rows"][5][0] == "fixed@example.com"
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 409
    original = client.get(f"/api/files/{fid}/preview").json()
    assert original["rows"][0][0] == "invalid-email"


def test_matching_scope_rejects_nonreplacement_actions():
    from app.models.requests import EditorRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="manual replacements only"):
        EditorRequest(revision=0, column="Name", row_index=0, scope="matching", action="trim_whitespace")


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    rate.clear()
    return TestClient(app)


def upload(client):
    response = client.post(
        "/api/files/upload",
        files={
            "file": (
                "editor.csv",
                b"Customer_ID,Name,Birth_Date,Salary,Email\n001, mary david ,2025-01-02,$100,invalid-email\n002,MARY DAVID,05/10/2025,200,mary@example.com\n003,Other,88-99-2089,NA,other@example.com\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["file_id"]


def test_undo_replays_later_steps_and_enforces_revision_and_session(client):
    fid = upload(client)
    client.post(f"/api/files/{fid}/editor/start")
    for revision, column, value in [(0, "Email", "fixed@example.com"), (1, "Name", "Custom Name")]:
        response = client.post(f"/api/files/{fid}/editor/fix", json={"revision": revision, "column": column, "row_index": 0, "action": "replace", "value": value, "confirmed": True})
        assert response.status_code == 200, response.text
    current = client.get(f"/api/files/{fid}/editor").json()
    change_id = current["changes"][0]["id"]
    url = f"/api/files/{fid}/editor/undo/{change_id}"
    assert TestClient(app).post(url + "?revision=2").status_code == 404
    assert client.post(url + "?revision=1").status_code == 409
    assert client.post(url + "?revision=2").status_code == 200
    after = client.get(f"/api/files/{fid}/editor").json()
    assert after["revision"] == 3
    assert len(after["changes"]) == 1
    assert after["preview"]["rows"][0][1] == "Custom Name"
    assert after["preview"]["rows"][0][4] == "invalid-email"
    assert client.post(url + "?revision=3").status_code == 409


def test_issue_navigation_finds_later_page_and_wraps(client):
    csv = "Salary\n" + "\n".join(["$100"] * 30 + ["unknown", "NA"])
    response = client.post("/api/files/upload", files={"file": ("later.csv", csv.encode(), "text/csv")})
    assert response.status_code == 200, response.text
    fid = response.json()["file_id"]
    assert client.post(f"/api/files/{fid}/editor/start").status_code == 200
    url = f"/api/files/{fid}/editor/next-issue?column=Salary&kind=odd_value"
    found = client.get(url).json()
    assert found["target"]["row_index"] == 30
    assert found["target"]["page"] == 2
    assert found["total"] == 1
    assert client.get(url + "&after=30").json()["target"]["row_index"] == 30
    missing_cell = client.get(f"/api/files/{fid}/editor/next-issue?column=Salary&kind=missing").json()
    assert missing_cell["target"]["row_index"] == 31
    assert TestClient(app).get(url).status_code == 404
    report = client.get(f"/api/files/{fid}/editor/download?format=report")
    assert report.headers["content-type"] == "application/pdf"
    assert ".pdf" in report.headers["content-disposition"]
    assert report.content.startswith(b"%PDF-")


def test_boolean_column_fix_is_detected_and_normalizes_entire_column(client):
    csv = b"Active\n1\nNo\nYes\nY\nTRUE\nFalse\n"
    fid = client.post("/api/files/upload", files={"file": ("boolean.csv", csv, "text/csv")}).json()["file_id"]
    started = client.post(f"/api/files/{fid}/editor/start").json()
    assert any(issue["kind"] == "boolean" for issue in started["preview"]["cell_issues"][0][0])
    response = client.post(f"/api/files/{fid}/editor/fix", json={"revision": 0, "column": "Active", "row_index": 0, "scope": "column", "action": "normalize_boolean", "confirmed": True})
    assert response.status_code == 200, response.text
    after = client.get(f"/api/files/{fid}/editor").json()
    assert [row[0] for row in after["preview"]["rows"]] == [True, False, True, True, True, False]
    assert client.get(f"/api/files/{fid}/editor/next-issue?column=Active&kind=boolean").json()["total"] == 0


def test_next_different_issue_skips_repeated_empty_cells(client):
    values = ["NA"] * 30 + [f"${100 + index}" for index in range(20)] + ["unknown"]
    csv = "Row_ID,Salary\n" + "\n".join(f"{index},{value}" for index, value in enumerate(values))
    fid = client.post("/api/files/upload", files={"file": ("different.csv", csv.encode(), "text/csv")}).json()["file_id"]
    client.post(f"/api/files/{fid}/editor/start")
    url = f"/api/files/{fid}/editor/next-issue?column=Salary&distinct_types=true"
    first = client.get(url).json()
    assert first["target"]["row_index"] == 0
    assert first["new_kinds"] == ["missing"]
    assert set(first["available_kinds"]) == {"missing", "odd_value", "type"}
    assert client.get(f"/api/files/{fid}/editor/next-issue?column=Row_ID&distinct_types=true").json()["available_kinds"] == []
    next_issue = client.get(url + "&after=0&seen_kinds=missing").json()
    assert next_issue["target"]["row_index"] == 50
    assert next_issue["target"]["page"] == 3
    seen = ",".join(first["new_kinds"] + next_issue["new_kinds"])
    done = client.get(url + "&after=50&seen_kinds=" + seen).json()
    assert done["target"] is None
    assert done["all_types_seen"] is True
    assert done["available_kinds"] == first["available_kinds"]


@pytest.mark.parametrize("replacement", [None, "2000-01-01"])
def test_bulk_invalid_dates_preserves_valid_ambiguous_missing_and_supports_undo(client, replacement):
    values = ["2020-01-15"] * 30 + ["2025-99-88", "88-99-2020", "05/10/2025", "NA"]
    csv = "Row_ID,Join_Date\n" + "\n".join(f"{index},{value}" for index, value in enumerate(values))
    fid = client.post("/api/files/upload", files={"file": ("dates.csv", csv.encode(), "text/csv")}).json()["file_id"]
    client.post(f"/api/files/{fid}/editor/start")
    response = client.post(f"/api/files/{fid}/editor/fix", json={"revision": 0, "column": "Join_Date", "row_index": 30, "scope": "invalid_dates", "action": "replace", "value": replacement, "confirmed": True})
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["changed_cells"] == 2
    sheet = client.get(f"/api/files/{fid}/editor?page=2").json()
    rows = sheet["preview"]["rows"]
    assert rows[5][1] == replacement
    assert rows[6][1] == replacement
    assert rows[7][1] == "05/10/2025"
    assert rows[8][1] is None
    assert rows[0][1] == "2020-01-15"
    change_id = sheet["changes"][0]["id"]
    assert client.post(f"/api/files/{fid}/editor/undo/{change_id}?revision=1").status_code == 200
    restored = client.get(f"/api/files/{fid}/editor?page=2").json()["preview"]["rows"]
    assert restored[5][1] == "2025-99-88"
    assert restored[6][1] == "88-99-2020"


def test_workspace_restore_keeps_confirmed_history_and_restricts_other_sessions(client):
    fid = upload(client)
    client.post(f"/api/files/{fid}/editor/start")
    client.post(f"/api/files/{fid}/editor/fix", json={"revision": 0, "column": "Email", "row_index": 0, "scope": "cell", "action": "replace", "value": "fixed@example.com", "confirmed": True})
    restored = client.get(f"/api/files/{fid}/workspace")
    assert restored.status_code == 200
    assert restored.json()["file_id"] == fid
    assert restored.json()["profile"]["rows"] == 3
    assert client.get(f"/api/files/{fid}/editor").json()["changes"][0]["column"] == "Email"
    assert TestClient(app).get(f"/api/files/{fid}/workspace").status_code == 404


def test_issue_scope_count_and_apply_change_only_selected_issue(client):
    csv = b"Row_ID,Amount\n1,10\n2,20\n3,30\n4,unknown\n5,40\n6,invalid\n7,50\n8,60\n9,NA"
    fid = client.post("/api/files/upload", files={"file": ("odd.csv", csv, "text/csv")}).json()["file_id"]
    client.post(f"/api/files/{fid}/editor/start")
    body = {"revision": 0, "column": "Amount", "row_index": 3, "scope": "issue", "action": "replace", "value": None, "parameters": {"issue_kind": "odd_value"}}
    counted = client.post(f"/api/files/{fid}/editor/fix", json=body)
    assert counted.status_code == 200, counted.text
    assert counted.json()["proposal"]["changed_cells"] == 2
    assert client.get(f"/api/files/{fid}/editor").json()["revision"] == 0
    body["confirmed"] = True
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    rows = client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"]
    assert rows[3][1] is None and rows[5][1] is None
    assert rows[0][1] == "10" and rows[8][1] is None


def test_basic_cleanup_preserves_identifiers_acronyms_and_ambiguous_dates():
    df = pd.DataFrame(
        {
            "Customer_ID": ["001", "002", "003"],
            "Name": [" mary david ", "MARY DAVID", "Other"],
            "Department": ["IT", "it", "HR"],
            "Birth_Date": ["2025-01-02", "05/10/2025", "88-99-2089"],
            "Email": ["Mary@example.com", "MARY@example.com", "x@y.com"],
        }
    )
    original = df.copy(deep=True)
    cleaned, logs = basic_cleanup(df)
    assert cleaned["Name"].tolist() == ["Mary David", "Mary David", "Other"]
    assert cleaned["Department"].tolist() == ["IT", "IT", "HR"]
    assert cleaned["Customer_ID"].tolist() == ["001", "002", "003"]
    assert cleaned["Birth_Date"].tolist() == original["Birth_Date"].tolist()
    assert cleaned["Email"].tolist() == original["Email"].tolist()
    assert any(l["modified_values"] for l in logs)
    pd.testing.assert_frame_equal(df, original)


def test_editor_annotations_preview_confirm_export_and_access(client):
    fid = upload(client)
    started = client.post(f"/api/files/{fid}/editor/start").json()
    assert started["preview"]["rows"][0][1] == "mary david"
    assert started["preview"]["cell_issues"][0][4][0]["kind"] == "email"
    assert any(
        i["kind"] == "ambiguous_date" for i in started["preview"]["cell_issues"][1][2]
    )
    assert any(
        i["kind"] == "invalid_date" for i in started["preview"]["cell_issues"][2][2]
    )
    assert started["preview"]["cell_issues"][2][3][0]["kind"] == "missing"
    body = {
        "revision": 0,
        "column": "Birth_Date",
        "row_index": 2,
        "action": "replace",
        "value": "2025-10-06",
    }
    preview = client.post(f"/api/files/{fid}/editor/fix", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["proposal"]["changed_cells"] == 1
    assert (
        client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"][2][2]
        == "88-99-2089"
    )
    body["confirmed"] = True
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    after = client.get(f"/api/files/{fid}/editor").json()
    assert after["revision"] == 1
    assert not any(issue["kind"] == "invalid_date" for issue in after["preview"]["cell_issues"][2][2])
    assert (
        client.get(f"/api/files/{fid}/preview").json()["rows"][0][1] == " mary david "
    )
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 409
    outsider = TestClient(app)
    assert outsider.get(f"/api/files/{fid}/editor").status_code == 404
    assert outsider.get(f"/api/files/{fid}/editor/download").status_code == 404
    csv = client.get(f"/api/files/{fid}/editor/download?format=csv")
    assert "2025-10-06" in csv.text and "001" in csv.text
    book = load_workbook(
        io.BytesIO(client.get(f"/api/files/{fid}/editor/download?format=xlsx").content)
    )
    assert book.active["A2"].value == "001"
    assert (
        client.get(f"/api/files/{fid}/editor/download?format=report_json").json()[
            "confirmed_changes"
        ][0]["action"]
        == "replace"
    )
    assert client.post(f"/api/files/{fid}/editor/start").json()["revision"] == 1
    assert client.delete(f"/api/files/{fid}").status_code == 200
    assert client.get(f"/api/files/{fid}/editor").status_code == 404


def test_column_currency_and_cell_imputation_keep_other_cells_unchanged(client):
    fid = upload(client)
    client.post(f"/api/files/{fid}/editor/start")
    body = {
        "revision": 0,
        "column": "Salary",
        "row_index": 0,
        "action": "normalize_currency",
        "scope": "column",
        "parameters": {"action": "remove"},
        "confirmed": True,
    }
    response = client.post(f"/api/files/{fid}/editor/fix", json=body)
    assert response.status_code == 200, response.text
    body.update(
        revision=1,
        row_index=2,
        scope="cell",
        action="impute_missing_values",
        parameters={"method": "mean"},
    )
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    values = client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"]
    assert [r[3] for r in values] == ["100", "200", 150]
    assert values[0][4] == "invalid-email"


def test_invalid_editor_requests_and_formula_safe_export(client):
    fid = upload(client)
    assert client.get(f"/api/files/{fid}/editor").status_code == 409
    client.post(f"/api/files/{fid}/editor/start")
    body = {
        "revision": 0,
        "column": "Name",
        "row_index": 0,
        "action": "replace",
        "scope": "column",
        "value": "X",
        "confirmed": True,
    }
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 422
    body.update(scope="cell", row_index=999)
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 422
    body.update(row_index=0, value="=1+1")
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    assert "'=1+1" in client.get(f"/api/files/{fid}/editor/download?format=csv").text
    assert client.get(f"/api/files/{fid}/editor?page=2&page_size=1").json()["preview"][
        "row_indices"
    ] == [1]


def test_editor_accepts_excel_and_retains_native_date_and_id(client):
    from datetime import datetime

    book = Workbook()
    book.active.append(["Customer_ID", "Name", "Birth_Date"])
    book.active.append(["001", " mary david ", datetime(2005, 3, 16)])
    buffer = io.BytesIO()
    book.save(buffer)
    uploaded = client.post(
        "/api/files/upload",
        files={
            "file": (
                "editor.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    fid = uploaded.json()["file_id"]
    response = client.post(f"/api/files/{fid}/editor/start")
    assert response.status_code == 200, response.text
    row = response.json()["preview"]["rows"][0]
    assert row[:2] == ["001", "mary david"]
    assert row[2].startswith("2005-03-16")


def test_editor_column_percentage_and_confirmed_duplicate_removal(client):
    data = b"Name,Rate\nA,10%\nB,20\nB,20\n"
    fid = client.post(
        "/api/files/upload", files={"file": ("notation.csv", data, "text/csv")}
    ).json()["file_id"]
    client.post(f"/api/files/{fid}/editor/start")
    body = {
        "revision": 0,
        "column": "Rate",
        "row_index": 0,
        "scope": "cell",
        "action": "normalize_percentage",
        "parameters": {"action": "remove"},
        "confirmed": True,
    }
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    rows = client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"]
    assert [r[1] for r in rows] == ["10", "20", "20"]
    body.update(
        revision=1,
        column="Name",
        scope="column",
        action="remove_duplicates",
        parameters={},
        confirmed=False,
    )
    preview = client.post(f"/api/files/{fid}/editor/fix", json=body).json()["proposal"]
    assert preview["changed_cells"] == 1
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["total_rows"] == 3
    body["confirmed"] = True
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    after = client.get(f"/api/files/{fid}/editor?page=9&page_size=1").json()["preview"]
    assert after["total_rows"] == 2 and after["page"] == 2
    assert after["row_indices"] == [1]
    assert not after["cell_issues"][0][0]


def test_editor_date_interpretation_and_new_whitespace_annotation(client):
    fid = upload(client)
    client.post(f"/api/files/{fid}/editor/start")
    body = {
        "revision": 0,
        "column": "Birth_Date",
        "row_index": 1,
        "scope": "cell",
        "action": "normalize_dates",
        "parameters": {"interpretation": "day_first"},
        "confirmed": True,
    }
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    data = client.get(f"/api/files/{fid}/editor").json()
    assert data["preview"]["rows"][1][2] == "2025-10-05"
    assert data["preview"]["rows"][2][2] == "88-99-2089"
    body.update(
        revision=1,
        column="Name",
        row_index=0,
        action="replace",
        value=" Mary ",
        parameters={},
    )
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    data = client.get(f"/api/files/{fid}/editor").json()
    assert any(i["kind"] == "whitespace" for i in data["preview"]["cell_issues"][0][1])
    body.update(revision=2, action="trim_whitespace")
    assert client.post(f"/api/files/{fid}/editor/fix", json=body).status_code == 200
    assert (
        client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"][0][1] == "Mary"
    )

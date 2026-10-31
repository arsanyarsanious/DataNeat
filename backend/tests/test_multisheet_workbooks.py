"""Verify the current, intentionally single-selected-sheet XLSX contract."""
import io
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app.core.file_parser import inspect_workbook, parse_file
from app.main import app, rate, store
from test_xlsx_formula_results import with_cached_results


def sample_workbook(include_boundary_tabs=True):
    workbook = Workbook()
    customers = workbook.active
    customers.title = "Customers"
    customers.append(["Customer_ID", "City", "Email"])
    customers.append([7, " Cairo ", "cairo@example.test"])
    customers["A2"].number_format = "00000"
    customers.append(["00123", "Aswan", "aswan@example.test"])
    customers.append(["00042", "Alexandria", "alex@example.test"])
    orders = workbook.create_sheet("Orders")
    orders.append(["Order_ID", "Amount", "Formula"])
    orders.append(["O01", 10, "=SUM(B2:B3)"])
    orders.append(["O02", 20, "plain"])
    orders.append(["O03", None, "=1+1"])
    events = workbook.create_sheet("Events")
    events.append(["Event_ID", "Event_Date", "Start_Time"])
    events.append(["E01", datetime(2024, 1, 1), "2:30 PM"])
    events.append(["E02", datetime(2024, 1, 2), "14:30:00"])
    events.append(["E03", datetime(2024, 1, 3), "08:00:00"])
    if include_boundary_tabs:
        workbook.create_sheet("Empty")
        workbook.create_sheet("Headers only").append(["NoData"])
        wide = workbook.create_sheet("Wider tab")
        wide.append(["A", "B", "C", "D"])
        wide.append([1, 2, 3, 4])
    # Import defaults to sheet position, not the workbook's active-tab setting.
    workbook.active = 2
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return with_cached_results(output.getvalue(), {"C2": ("n", 30), "C4": ("n", 2)}, sheet_number=2)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "root", tmp_path)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    store.jobs.clear()
    store.access.clear()
    rate.clear()
    return TestClient(app)


def upload(client, content, sheet=None):
    return client.post(
        "/api/files/upload",
        files={"file": ("multi-sheet-check.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={} if sheet is None else {"sheet": sheet},
    )


def workflow_job(client, file_id, revision, operation, **parameters):
    response = client.post(f"/api/files/{file_id}/workflow/jobs", json={
        "revision": revision, "operation": operation, **parameters,
    })
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    for _ in range(300):
        rate.clear()
        status = client.get(f"/api/workflow-jobs/{job_id}")
        assert status.status_code == 200, status.text
        status = status.json()
        if status["status"] not in ("queued", "running"):
            assert status["status"] == "completed", status
            return status
        time.sleep(.01)
    pytest.fail("Worksheet workflow did not finish")


def test_default_import_lists_tabs_but_reads_first_not_active_sheet():
    content = sample_workbook()
    frame, metadata = parse_file(content, "multi-sheet-check.xlsx")
    assert metadata["sheets"] == ["Customers", "Orders", "Events", "Empty", "Headers only", "Wider tab"]
    assert metadata["worksheet"] == "Customers"
    assert list(frame.columns) == ["Customer_ID", "City", "Email"]
    assert len(frame) == 3
    assert frame["Customer_ID"].tolist() == ["00007", "00123", "00042"]
    assert frame["City"].tolist() == [" Cairo ", "Aswan", "Alexandria"]
    assert metadata["formula_cells"] == 0


def test_explicit_sheet_selection_imports_formula_results_and_dates():
    content = sample_workbook()
    orders, order_metadata = parse_file(content, "multi-sheet-check.xlsx", "Orders")
    events, event_metadata = parse_file(content, "multi-sheet-check.xlsx", "Events")
    assert order_metadata["worksheet"] == "Orders"
    assert order_metadata["formula_cells"] == 2
    assert orders["Formula"].tolist() == [30, "plain", 2]
    assert event_metadata["worksheet"] == "Events"
    assert events.at[0, "Event_Date"] == datetime(2024, 1, 1)
    assert events["Start_Time"].tolist() == ["2:30 PM", "14:30:00", "08:00:00"]


@pytest.mark.parametrize("sheet", ["Empty", "Headers only"])
def test_empty_selected_tab_is_rejected_without_falling_back_to_another_tab(sheet):
    with pytest.raises(ValueError, match="(1–200 columns|no data rows)"):
        parse_file(sample_workbook(), "multi-sheet-check.xlsx", sheet)


def test_invalid_sheet_name_does_not_create_a_workspace(client):
    response = upload(client, sample_workbook(), "Does not exist")
    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown worksheet"
    assert list(store.root.glob("*.bin")) == []


def test_selected_tab_dimensions_are_checked_independently(monkeypatch):
    import app.core.file_parser as parser
    monkeypatch.setattr(parser, "MAX_COLUMNS", 3)
    content = sample_workbook()
    assert len(parse_file(content, "multi-sheet-check.xlsx", "Customers")[0]) == 3
    with pytest.raises(ValueError, match="dimensions exceed limits"):
        parse_file(content, "multi-sheet-check.xlsx", "Wider tab")


def test_empty_first_tab_blocks_default_upload_but_named_valid_tab_can_import(client):
    workbook = Workbook()
    workbook.active.title = "Empty first"
    valid = workbook.create_sheet("Valid data")
    valid.append(["ID", "Value"])
    valid.append(["001", "Cairo"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    assert upload(client, buffer.getvalue()).status_code == 422
    selected = upload(client, buffer.getvalue(), "Valid data")
    assert selected.status_code == 200, selected.text
    assert selected.json()["metadata"]["sheets"] == ["Empty first", "Valid data"]
    assert selected.json()["preview"]["rows"] == [["001", "Cairo"]]


def test_sheet_workspaces_clean_independently_and_export_only_selected_table(client):
    content = sample_workbook()
    first = upload(client, content, "Customers")
    second = upload(client, content, "Orders")
    assert first.status_code == second.status_code == 200
    first_id, second_id = first.json()["file_id"], second.json()["file_id"]
    assert first_id != second_id
    for file_id in (first_id, second_id):
        assert client.post(f"/api/files/{file_id}/workflow/init").status_code == 200
    workflow_job(client, first_id, 0, "decision", decision={
        "kind": "fix", "body": {"revision": 0, "column": "City", "row_index": 0,
        "scope": "column", "action": "trim_whitespace", "parameters": {}, "confirmed": True},
    })
    current = client.get(f"/api/files/{first_id}/editor").json()
    untouched = client.get(f"/api/files/{second_id}/editor").json()
    assert current["revision"] == 1
    assert current["preview"]["rows"][0][:2] == ["00007", "Cairo"]
    assert untouched["revision"] == 0
    assert untouched["preview"]["rows"][0] == ["O01", 10, 30]
    session = client.cookies.get("dataneat_session")
    original = store.get(first_id, session)
    assert original["original_bytes"] == content
    assert original["df"].at[0, "City"] == " Cairo "
    assert original["editor_df"].at[0, "City"] == "Cairo"
    restored = client.get(f"/api/files/{first_id}/workspace").json()
    assert restored["metadata"]["worksheet"] == "Customers"
    assert restored["metadata"]["sheets"] == first.json()["metadata"]["sheets"]
    assert "Only the selected worksheet" in restored["metadata"]["compatibility_warning"]
    for file_id, revision, expected_header in (
        (first_id, 1, ["Customer_ID", "City", "Email"]),
        (second_id, 0, ["Order_ID", "Amount", "Formula"]),
    ):
        status = workflow_job(client, file_id, revision, "export", format="xlsx")
        response = client.get(status["result"]["download"])
        assert response.status_code == 200
        workbook = load_workbook(io.BytesIO(response.content), data_only=False)
        assert workbook.sheetnames == ["Sheet1"]
        assert [cell.value for cell in workbook.active[1]] == expected_header
        assert workbook.active.max_row == 4
        if file_id == first_id:
            assert workbook.active["A2"].value == "00007"
            assert workbook.active["B2"].value == "Cairo"
        else:
            assert workbook.active["C2"].value == 30
            assert workbook.active["C2"].data_type != "f"
        workbook.close()
    # Both original workbooks still contain all tabs and executable formula text.
    original_book = load_workbook(io.BytesIO(store.get(first_id, session)["original_bytes"]))
    assert original_book.sheetnames == first.json()["metadata"]["sheets"]
    assert original_book["Orders"]["C2"].data_type == "f"
    original_book.close()


def test_inspection_lists_tabs_and_reported_dimensions_without_selecting():
    result = inspect_workbook(sample_workbook(), "multi-sheet-check.xlsx")
    assert result["filename"] == "multi-sheet-check.xlsx"
    assert result["selected_sheet"] is None
    assert result["limits"] == {"max_rows": 100000, "max_columns": 200, "max_sheets": 1000}
    assert [sheet["name"] for sheet in result["sheets"]] == ["Customers", "Orders", "Events", "Empty", "Headers only", "Wider tab"]
    assert result["sheets"][0] == {"name": "Customers", "rows": 3, "columns": 3,
                                    "hidden": False, "selectable": True}
    for sheet in result["sheets"][3:5]:
        assert sheet["rows"] == 0 and not sheet["selectable"]
        assert "No data rows" in sheet["reason"]


def test_inspection_marks_hidden_and_very_hidden_tabs_without_silently_omitting_them():
    workbook = load_workbook(io.BytesIO(sample_workbook(False)))
    workbook["Orders"].sheet_state = "hidden"
    workbook["Events"].sheet_state = "veryHidden"
    content = io.BytesIO()
    workbook.save(content)
    workbook.close()
    sheets = inspect_workbook(content.getvalue(), "hidden.xlsx")["sheets"]
    assert [sheet["hidden"] for sheet in sheets] == [False, True, True]
    assert all(sheet["selectable"] for sheet in sheets)


def test_inspection_does_not_profile_import_or_create_records_even_with_empty_first_tab(client, monkeypatch):
    import app.main as main
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Inspect must not import or analyze cell data")
    monkeypatch.setattr(main, "profile_dataframe", forbidden)
    monkeypatch.setattr(main, "parse_file", forbidden)
    workbook = Workbook()
    workbook.active.title = "Empty first"
    populated = workbook.create_sheet("Customer data")
    populated.append(["ID", "City"])
    populated.append(["001", "Cairo"])
    content = io.BytesIO()
    workbook.save(content)
    workbook.close()
    response = client.post("/api/files/inspect-workbook", files={"file": ("C:\\folder\\choice.xlsx", content.getvalue())})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["filename"] == "choice.xlsx"
    assert result["selected_sheet"] is None
    assert not result["sheets"][0]["selectable"]
    assert result["sheets"][1] == {"name": "Customer data", "rows": 1, "columns": 2,
                                   "hidden": False, "selectable": True}
    assert list(store.root.iterdir()) == []


@pytest.mark.parametrize("name,content,detail", [
    ("data.csv", b"A,B\n1,2\n", "XLSX workbook"),
    ("broken.xlsx", b"not-a-zip", "Invalid XLSX"),
    ("empty.xlsx", b"", "file is empty"),
])
def test_inspection_rejects_invalid_uploads_without_records(client, name, content, detail):
    response = client.post("/api/files/inspect-workbook", files={"file": (name, content)})
    assert response.status_code == 422, response.text
    assert detail in response.json()["detail"]
    assert list(store.root.iterdir()) == []


def test_inspection_obeys_streamed_upload_limit(client, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "MAX_UPLOAD", 4)
    response = client.post("/api/files/inspect-workbook", files={"file": ("book.xlsx", b"12345")})
    assert response.status_code == 413
    assert list(store.root.iterdir()) == []


def test_inspection_obeys_expanded_zip_and_tab_count_limits(monkeypatch):
    import app.core.file_parser as parser
    content = sample_workbook(False)
    monkeypatch.setattr(parser, "MAX_WORKBOOK_EXPANDED_BYTES", 100)
    with pytest.raises(ValueError, match="expands beyond"):
        inspect_workbook(content, "book.xlsx")
    monkeypatch.setattr(parser, "MAX_WORKBOOK_EXPANDED_BYTES", 100 * 1024 * 1024)
    monkeypatch.setattr(parser, "MAX_INSPECT_SHEETS", 2)
    with pytest.raises(ValueError, match="no more than 2 tabs"):
        inspect_workbook(content, "book.xlsx")


def test_inspection_never_walks_cell_rows_to_report_limits(monkeypatch):
    import app.core.file_parser as parser
    class Worksheet:
        def __init__(self, row_count, column_count):
            self.max_row, self.max_column = row_count, column_count
            self.sheet_state = "visible"
        def iter_rows(self):
            raise AssertionError("Inspection must not scan worksheet rows")
    class MetadataOnlyWorkbook:
        sheetnames = ["OK", "Too many rows", "Too many columns", "Unknown bounds"]
        sheets = {"OK": Worksheet(4, 2), "Too many rows": Worksheet(100002, 1),
                  "Too many columns": Worksheet(2, 201), "Unknown bounds": Worksheet(None, None)}
        closed = False
        def __getitem__(self, name):
            return self.sheets[name]
        def close(self):
            self.closed = True
    workbook = MetadataOnlyWorkbook()
    monkeypatch.setattr(parser, "load_workbook", lambda *_args, **_kwargs: workbook)
    result = inspect_workbook(sample_workbook(False), "limits.xlsx")
    assert result["sheets"][0]["selectable"]
    assert all(not sheet["selectable"] for sheet in result["sheets"][1:])
    assert "100,000 data rows or 200 columns" in result["sheets"][1]["reason"]
    assert "dimensions are unavailable" in result["sheets"][3]["reason"]
    assert workbook.closed


def test_inspection_chart_tab_is_listed_but_not_selectable():
    from openpyxl.chart import BarChart, Reference
    workbook = load_workbook(io.BytesIO(sample_workbook(False)))
    chart_tab = workbook.create_chartsheet("Chart only")
    chart = BarChart()
    chart.add_data(Reference(workbook["Orders"], min_col=2, min_row=1, max_row=3), titles_from_data=True)
    chart_tab.add_chart(chart)
    content = io.BytesIO()
    workbook.save(content)
    workbook.close()
    result = inspect_workbook(content.getvalue(), "chart.xlsx")
    chart_info = result["sheets"][-1]
    assert chart_info["name"] == "Chart only"
    assert not chart_info["selectable"] and "chart" in chart_info["reason"]


def test_inspection_remains_behind_existing_verified_account_boundary(client, monkeypatch):
    import app.main as main
    from fastapi import HTTPException
    monkeypatch.setattr(main.identity, "configuration", lambda: {"enabled": True})
    def deny(_token):
        raise HTTPException(401, "Please sign in to continue.")
    monkeypatch.setattr(main.identity, "verify", deny)
    response = client.post("/api/files/inspect-workbook", files={"file": ("book.xlsx", sample_workbook(False))})
    assert response.status_code == 401
    assert list(store.root.iterdir()) == []

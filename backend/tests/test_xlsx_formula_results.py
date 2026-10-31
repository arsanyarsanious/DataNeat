"""Real XLSX caches, not expression evaluation, supply imported formula values."""
import io
import time
import zipfile
from datetime import datetime
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from openpyxl.utils.datetime import to_excel

from app.core.file_parser import parse_file
from app.main import app, rate, store

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def with_cached_results(content, results, sheet_number=1, transform=None):
    """Add Excel-style saved results to formula fixtures written by openpyxl."""
    output = io.BytesIO()
    path = f"xl/worksheets/sheet{sheet_number}.xml"
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == path:
                root = ElementTree.fromstring(data)
                for cell in root.iter(f"{NS}c"):
                    coordinate = cell.get("r")
                    if coordinate not in results:
                        continue
                    kind, result = results[coordinate]
                    cell.attrib.pop("t", None)
                    if kind != "n":
                        cell.set("t", kind)
                    value = cell.find(f"{NS}v")
                    if value is None:
                        value = ElementTree.SubElement(cell, f"{NS}v")
                    value.text = "" if result is None else str(result)
                if transform:
                    transform(root)
                data = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(info, data)
    return output.getvalue()


def workbook_bytes(workbook):
    data = io.BytesIO()
    workbook.save(data)
    workbook.close()
    return data.getvalue()


@pytest.mark.parametrize("kind,saved,expected", [
    ("n", 35, 35), ("n", 0, 0), ("n", -12.5, -12.5),
    ("b", 0, False), ("b", 1, True), ("str", "Total", "Total"),
    ("str", "", None), ("str", "=literal result", "=literal result"),
    ("e", "#DIV/0!", "#DIV/0!"),
])
def test_imports_typed_saved_formula_results_without_expression(kind, saved, expected):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Result"])
    sheet.append(["=SUM(10,25)"])
    content = with_cached_results(workbook_bytes(workbook), {"A2": (kind, saved)})
    data, metadata = parse_file(content, "results.xlsx")
    assert data.iat[0, 0] == expected
    if kind == "b":
        assert type(data.iat[0, 0]) is bool
    assert metadata["formula_cells"] == 1
    assert metadata["formula_error_cells"] == (1 if kind == "e" else 0)
    assert "last saved Excel results" in metadata["formula_notice"]
    assert "SUM" not in str(data.iat[0, 0])


def test_formula_dates_zero_padded_identifiers_and_headers_use_saved_values():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["=\"Calculated ID\"", "Date"])
    sheet.append(["=100+23", "=DATE(2024,2,29)"])
    sheet["A2"].number_format = "00000"
    sheet["B2"].number_format = "dd/mm/yyyy"
    content = with_cached_results(workbook_bytes(workbook), {
        "A1": ("str", "Calculated ID"), "A2": ("n", 123),
        "B2": ("n", to_excel(datetime(2024, 2, 29))),
    })
    data, metadata = parse_file(content, "typed.xlsx")
    assert list(data.columns) == ["Calculated ID", "Date"]
    assert data.iat[0, 0] == "00123"
    assert data.iat[0, 1] == datetime(2024, 2, 29)
    assert metadata["formula_cells"] == 3


def test_uncached_formulas_are_rejected_instead_of_becoming_missing_or_zero():
    workbook = Workbook()
    workbook.active.title = "Sales"
    workbook.active.append(["Amount", "Total"])
    workbook.active.append([10, "=SUM(A2:A3)"])
    workbook.active.append([20, "=IF(TRUE,\"\",\"\")"])
    with pytest.raises(ValueError) as error:
        parse_file(workbook_bytes(workbook), "uncached.xlsx")
    message = str(error.value)
    assert "Sales" in message and "B2, B3" in message
    assert "2 formula cells without saved results" in message
    assert "recalculate the formulas, save it, and upload it again" in message
    assert "=SUM" not in message and "=IF" not in message


def test_only_selected_sheet_requires_formula_results():
    workbook = Workbook()
    workbook.active.title = "Safe"
    workbook.active.append(["Value"])
    workbook.active.append([7])
    other = workbook.create_sheet("Uncalculated")
    other.append(["Value"])
    other.append(["=1+1"])
    content = workbook_bytes(workbook)
    data, metadata = parse_file(content, "selected.xlsx", "Safe")
    assert data.iat[0, 0] == 7 and metadata["formula_cells"] == 0
    with pytest.raises(ValueError, match="without saved results"):
        parse_file(content, "selected.xlsx", "Uncalculated")


def test_shared_array_and_external_reference_formulas_use_only_cached_results():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Value"])
    sheet.append(["=1+1"])
    sheet.append(["=2+1"])
    sheet.append(["=SUM(A2:A3)"])
    sheet.append(["='https://example.test/[remote.xlsx]Data'!A1"])
    def special_forms(root):
        cells = {cell.get("r"): cell for cell in root.iter(f"{NS}c")}
        cells["A2"].find(f"{NS}f").attrib.update({"t": "shared", "si": "0", "ref": "A2:A3"})
        dependent = cells["A3"].find(f"{NS}f")
        dependent.attrib.update({"t": "shared", "si": "0"})
        dependent.text = None
        cells["A4"].find(f"{NS}f").attrib.update({"t": "array", "ref": "A4"})
    content = with_cached_results(workbook_bytes(workbook), {
        "A2": ("n", 2), "A3": ("n", 3), "A4": ("n", 5), "A5": ("n", 42),
    }, transform=special_forms)
    data, metadata = parse_file(content, "shared.xlsx")
    assert data["Value"].tolist() == [2, 3, 5, 42]
    assert metadata["formula_cells"] == 4


def test_formula_like_text_is_preserved_and_not_counted_as_a_formula():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Text"])
    sheet.append(["=literal-not-a-formula"])
    sheet["A2"].data_type = "s"
    data, metadata = parse_file(workbook_bytes(workbook), "literal.xlsx")
    assert data.iat[0, 0] == "=literal-not-a-formula"
    assert metadata["formula_cells"] == 0
    assert metadata["formula_notice"] is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "root", tmp_path)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    store.jobs.clear()
    store.access.clear()
    rate.clear()
    return TestClient(app)


def test_uncached_formula_upload_does_not_create_a_file_record(client):
    workbook = Workbook()
    workbook.active.append(["Value"])
    workbook.active.append(["=1+1"])
    result = client.post("/api/files/upload", files={"file": ("uncached.xlsx", workbook_bytes(workbook))})
    assert result.status_code == 422
    assert "without saved results" in result.json()["detail"]
    assert not list(store.root.glob("*.bin"))


def test_formula_results_flow_through_preview_analysis_and_values_only_export(client):
    workbook = Workbook()
    workbook.active.append(["ID", "Value"])
    workbook.active.append(["001", "=1+1"])
    content = with_cached_results(workbook_bytes(workbook), {"B2": ("n", 2)})
    result = client.post("/api/files/upload", files={"file": ("values.xlsx", content)})
    assert result.status_code == 200, result.text
    upload = result.json()
    assert upload["preview"]["rows"] == [["001", 2]]
    assert upload["metadata"]["formula_cells"] == 1
    file_id = upload["file_id"]
    assert client.post(f"/api/files/{file_id}/workflow/init").status_code == 200
    editor = client.get(f"/api/files/{file_id}/editor").json()
    assert editor["preview"]["rows"] == [["001", 2]]
    response = client.post(f"/api/files/{file_id}/workflow/jobs", json={"revision": 0, "operation": "export", "format": "xlsx"})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    for _ in range(300):
        rate.clear()
        status = client.get(f"/api/workflow-jobs/{job_id}").json()
        if status["status"] not in ("queued", "running"):
            break
        time.sleep(.01)
    assert status["status"] == "completed", status
    exported = client.get(status["result"]["download"])
    saved = load_workbook(io.BytesIO(exported.content), data_only=False)
    assert saved.active["B2"].value == 2 and saved.active["B2"].data_type != "f"
    saved.close()
    stored = store.get(file_id, client.cookies.get("dataneat_session"))
    assert stored["original_bytes"] == content
    original = load_workbook(io.BytesIO(stored["original_bytes"]), data_only=False)
    assert original.active["B2"].value == "=1+1"
    original.close()

import io
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Color
from test_workflows import client, job, wait
from test_xlsx_formula_results import with_cached_results


def color_upload(client):
    book = Workbook(); sheet = book.active; sheet.title = "Colored"
    sheet.append(["Phone", "Amount"])
    sheet.append(["00123", "=2+3"])
    sheet.append(["00234", 5])
    sheet.append(["00345", 13])
    sheet["A2"].fill = PatternFill("solid", fgColor="FFFF0000")
    sheet["A3"].fill = PatternFill("solid", fgColor=Color(indexed=5))
    sheet["B3"].fill = PatternFill("solid", fgColor=Color(theme=4, tint=0.5))
    sheet["A4"].fill = PatternFill("solid", fgColor="00FF00")
    other = book.create_sheet("Other"); other.append(["X"]); other.append(["Y"])
    raw = io.BytesIO(); book.save(raw)
    data = with_cached_results(raw.getvalue(), {"B2": ("n", "5")})
    response = client.post("/api/files/upload", files={"file": ("colors.xlsx", data)}, data={"sheet": "Colored"})
    assert response.status_code == 200, response.text
    fid = response.json()["file_id"]
    init = client.post(f"/api/files/{fid}/workflow/init")
    assert init.status_code == 200, init.text
    return fid, init.json()


def test_source_colors_are_opt_in_and_do_not_modify_workflow(client):
    fid, initial = color_upload(client)
    assert initial["original_colors"]["status"] == "off"
    assert "original_fills" not in initial["preview"]
    assert initial["preview"]["rows"][0][1] == 5
    colored = client.get(f"/api/files/{fid}/editor?original_colors=true").json()
    assert colored["original_colors"]["status"] == "ready"
    assert colored["preview"]["original_fills"][0] == ["#FF0000", None]
    assert colored["preview"]["original_fills"][1][0] == "#FFFF00"
    assert colored["preview"]["original_fills"][1][1].startswith("#")
    assert colored["revision"] == initial["revision"]
    assert colored["changes"] == initial["changes"]
    assert colored["preview"]["rows"] == initial["preview"]["rows"]
    plain = client.get(f"/api/files/{fid}/editor").json()
    assert "original_fills" not in plain["preview"]


def test_colors_remain_aligned_after_rename_and_paging(client):
    fid, _ = color_upload(client)
    result = wait(client, job(client, fid, 0, "decision", decision={"kind": "rename", "column": "Phone", "settings": {"name": "Serial"}}))
    assert result["status"] == "completed", result
    page = client.get(f"/api/files/{fid}/editor?original_colors=true&page=2&page_size=1").json()
    assert page["preview"]["row_indices"] == [1]
    assert page["preview"]["original_fills"][0][0] == "#FFFF00"


def test_csv_does_not_offer_original_colors(client):
    from test_workflows import upload
    fid, _ = upload(client)
    sheet = client.get(f"/api/files/{fid}/editor?original_colors=true").json()
    assert sheet["original_colors"]["status"] == "unsupported"
    assert "original_fills" not in sheet["preview"]


def test_original_colors_follow_survivors_after_duplicate_removal(client):
    fid, _ = color_upload(client)
    result = wait(client, job(client, fid, 0, "decision", decision={"kind": "fix", "body": {
        "revision": 0, "column": "Amount", "row_index": 0, "scope": "column",
        "action": "remove_duplicates", "parameters": {"subset": ["Amount"]}}}))
    assert result["status"] == "completed", result
    sheet = client.get(f"/api/files/{fid}/editor?original_colors=true").json()
    assert sheet["preview"]["row_indices"] == [0, 2]
    assert [r[0] for r in sheet["preview"]["original_fills"]] == ["#FF0000", "#00FF00"]


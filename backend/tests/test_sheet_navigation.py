import pandas as pd
import pytest
from app.core.sheet_navigation import find_value, compare_original
from test_workflows import client, upload, job, wait
from fastapi.testclient import TestClient
from app.main import app, rate


def test_search_crosses_pages_and_keeps_original_row_indices():
    df = pd.DataFrame({"City": ["Cairo"] * 30, "Amount": list(range(30))}, index=range(10, 40))
    result = find_value(df, "CAIRO", after=24)
    assert result["total_rows"] == 30
    assert result["target"] == {"row_index": 35, "position": 25, "page": 2, "column": "City"}
    assert find_value(df, "Cairo", after=29)["target"] is None
    assert find_value(df, "29", "Amount")["target"]["row_index"] == 39
    with pytest.raises(ValueError): find_value(df, "x", "Missing")


def test_comparison_uses_original_and_handles_rename_removed_rows_and_undo():
    original = pd.DataFrame({"City": [" Cairo ", "GIZA", None], "N": [1, 2, 3]})
    current = pd.DataFrame({"Town": ["Cairo", None], "N": [1, 3]}, index=[0, 2])
    record = {"df": original, "editor_df": current, "editor_revision": 3, "editor_changes": [{"action": "rename_column", "column": "City", "parameters": {"name": "Town"}}]}
    result = compare_original(record)
    assert result["total"] == 3
    assert result["renamed_columns"] == [{"before": "City", "after": "Town"}]
    assert result["rows"][0]["before"] == " Cairo "
    assert sum(r["removed_row"] for r in result["rows"]) == 2
    record.update(editor_df=original.copy(), editor_changes=[])
    assert compare_original(record)["total"] == 0


def test_comparison_pagination_does_not_repeat_or_omit_cells():
    original = pd.DataFrame({"A": ["old"]*60, "B": ["old"]*20+[None]*40})
    record = {"df": original, "editor_df": original.replace("old", "new"), "editor_changes": [], "editor_revision": 1}
    first, second = compare_original(record, 1), compare_original(record, 2)
    assert first["total"] == second["total"] == 80
    assert len(first["rows"]) == 50 and len(second["rows"]) == 30
    assert len({(r["row_index"], r["column"]) for r in first["rows"]+second["rows"]}) == 80


def test_navigation_is_owner_scoped_and_acceptance_does_not_change_values(client):
    fid, state = upload(client, b"ID,City\n001,CAIRO\n002,Cairo\n")
    assert client.get(f"/api/files/{fid}/editor/search", params={"q": "cairo"}).json()["total_rows"] == 2
    assert client.get(f"/api/files/{fid}/editor/compare").json()["total"] == 0
    outsider = TestClient(app)
    for path in ("search?q=cairo", "compare"):
        rate.clear()
        assert outsider.get(f"/api/files/{fid}/editor/{path}").status_code in (403, 404)
    result = wait(client, job(client, fid, state["revision"], "decision", decision={"kind": "ignore", "column": "City", "issue": "capitalization", "value": "CAIRO", "reason": "Intended value"}))
    assert result["status"] == "completed"
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0][1] == "CAIRO"
    assert not current["preview"]["cell_issues"][0][1]
    assert client.get(f"/api/files/{fid}/editor/compare").json()["total"] == 0

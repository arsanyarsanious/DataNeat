import pandas as pd
import pytest
from app.core.imputation import impute_missing_values, recommendation
from test_workflows import client, upload, job, wait


@pytest.mark.parametrize("values,expected", [
    (["2024-01-01", None, "2024-01-05"], "2024-01-03"),
    (["2024-01-01", None, "2024-01-04"], "2024-01-02"),
    (["2024-02-28", None, "2024-03-01"], "2024-02-29"),
    (["13/01/2024", None, "17/01/2024"], "15/01/2024"),
    (["2024-01-01T10:00:00+02:00", None, "2024-01-01T14:00:00+02:00"], "2024-01-01T12:00:00+02:00"),
])
def test_date_median_preserves_observations_and_formats(values, expected):
    df = pd.DataFrame({"Birth_Date": values})
    original = df.copy(deep=True)
    result, detail = impute_missing_values(df, "Birth_Date", "median", {})
    assert result.loc[1, "Birth_Date"] == expected
    assert result.loc[0, "Birth_Date"] == values[0] and result.loc[2, "Birth_Date"] == values[2]
    assert detail["imputed_count"] == 1
    assert "median" in recommendation(df.Birth_Date, "date")["available_methods"]
    pd.testing.assert_frame_equal(df, original)


def test_group_date_median_keeps_entities_separate():
    df = pd.DataFrame({"Entity": ["A"]*3+["B"]*3, "Join_Date": ["2020-01-01", None, "2020-01-05", "2024-01-01", None, "2024-01-05"]})
    result, _ = impute_missing_values(df, "Join_Date", "group_median", {"group_by": ["Entity"]})
    assert result.Join_Date.tolist() == ["2020-01-01", "2020-01-03", "2020-01-05", "2024-01-01", "2024-01-03", "2024-01-05"]


def test_old_saved_profile_exposes_date_median_without_rewriting_values():
    from app.main import editor_response
    from app.core.profiler import profile_dataframe
    df = pd.DataFrame({"Birth_Date": ["2024-01-01", None, "2024-01-05"]})
    profile = profile_dataframe(df)
    profile["columns"][0]["imputation"]["available_methods"] = ["mode", "constant"]
    record = {"editor_df": df, "editor_profile": profile, "editor_revision": 7, "editor_basic_log": [], "editor_changes": []}
    response = editor_response(record)
    assert "median" in response["profile"]["columns"][0]["imputation"]["available_methods"]
    assert response["revision"] == 7 and df.loc[1, "Birth_Date"] is None


@pytest.mark.parametrize("bad", ["01/02/2024", "2024-99-99"])
def test_date_median_blocks_unresolved_observations(bad):
    df = pd.DataFrame({"Birth_Date": ["2024-01-01", "2024-01-05", None, bad]})
    with pytest.raises(ValueError, match="spreadsheet row 5"):
        impute_missing_values(df, "Birth_Date", "median", {})


def test_date_median_uses_known_slash_format_and_is_undoable(client):
    fid, state = upload(client, b"ID,Birth_Date\n001,2024-01-01\n002,\n003,2024-01-05\n")
    normalized = wait(client, job(client, fid, state["revision"], "decision", decision={"kind":"fix", "body":{"revision":state["revision"],"column":"Birth_Date","row_index":0,"scope":"column","action":"normalize_dates","parameters":{"interpretation":"preserve","output_format":"DD/MM/YYYY"}}}))
    assert normalized["status"] == "completed"
    revision = normalized["result"]["revision"]
    filled = wait(client, job(client, fid, revision, "decision", decision={"kind":"fix", "body":{"revision":revision,"column":"Birth_Date","row_index":1,"scope":"cell","action":"impute_missing_values","parameters":{"method":"median"}}}))
    assert filled["status"] == "completed", filled
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][1][1] == "03/01/2024"
    assert not current["preview"]["cell_issues"][1][1]
    undo = wait(client, job(client, fid, current["revision"], "undo", step_id=current["changes"][-1]["id"]))
    assert undo["status"] == "completed"
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"][1][1] == state["preview"]["rows"][1][1]

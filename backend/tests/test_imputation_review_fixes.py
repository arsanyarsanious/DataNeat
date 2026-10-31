import pandas as pd
import pytest
from app.core.imputation import impute_missing_values
from app.core.interactive import propose
from app.core.workflow import ensure_workflow, profile_record, apply_decision, replay_without, estimated_cells, known_date_formats
from app.models.requests import EditorRequest


def record(values, column="Birth_Date"):
    # Repeated gaps are separate observations, not duplicate whole records.
    result={"editor_df":pd.DataFrame({column:values,"Row_ID":[f"row-{i}" for i in range(len(values))]}),"editor_revision":0,"editor_changes":[]}
    ensure_workflow(result);profile_record(result)
    return result


def fill(rec, row, method="median", column="Birth_Date", **parameters):
    entry=apply_decision(rec,{"kind":"fix","body":{"revision":rec["editor_revision"],"column":column,"row_index":row,"scope":"cell","action":"impute_missing_values","parameters":{"method":method,**parameters}}})
    profile_record(rec)
    return entry


def test_cell_scope_audit_and_distribution_describe_only_actual_changes():
    df=pd.DataFrame({"Birth_Date":["2024-01-01",None,None,None,"2024-01-05"]})
    result, detail=propose(df,EditorRequest(revision=0,column="Birth_Date",row_index=1,scope="cell",action="impute_missing_values",parameters={"method":"median"}))
    audit=detail["imputation"]
    assert detail["changed_cells"] == audit["imputed_count"] == 1
    assert audit["missing_before"] == 3 and audit["missing_after"] == 2
    assert [c["row_index"] for c in audit["imputed_cells"]] == [1]
    assert audit["distribution_after"]["observed_count"] == 3
    assert result.loc[2,"Birth_Date"] is None


def test_earlier_cell_scope_audit_is_repaired_without_changing_data_or_revision():
    rec=record(["2024-01-01",None,None,None,"2024-01-05"])
    entry=fill(rec,1)
    entry["imputation"].update(imputed_count=3,missing_after=0,imputed_cells=[{"row_index":i} for i in (1,2,3)])
    before=rec["editor_df"].copy(deep=True)
    revision=rec["editor_revision"]
    ensure_workflow(rec)
    assert entry["imputation"]["imputed_count"] == 1 and entry["imputation"]["missing_after"] == 2
    assert entry["imputation"]["distribution_after"] == {}
    assert rec["editor_revision"] == revision
    pd.testing.assert_frame_equal(rec["editor_df"],before)


@pytest.mark.parametrize("column,values,constant,expected", [
    ("Birth_Date",["2024-01-01",None,None,"2024-01-05"],"2024-01-02","2024-01-03"),
    ("Amount",[10,None,None,30],12,20),
])
def test_previous_placeholders_never_become_statistical_sources(column, values, constant, expected):
    rec=record(values,column)
    fill(rec,1,"constant",column,value=constant)
    entry=fill(rec,2,"median",column)
    assert rec["editor_df"].loc[2,column] == expected
    assert entry["imputation"]["excluded_estimates"] == 1


def test_previous_statistical_estimate_is_excluded_after_rename_and_formatting():
    rec=record(["2024-01-01",None,None,"2024-01-05"])
    fill(rec,1,date_rounding="ceil")
    apply_decision(rec,{"kind":"rename","column":"Birth_Date","settings":{"name":"Joined"}})
    profile_record(rec)
    apply_decision(rec,{"kind":"fix","body":{"revision":rec["editor_revision"],"column":"Joined","row_index":0,"scope":"column","action":"normalize_dates","parameters":{"interpretation":"preserve","output_format":"DD/MM/YYYY"}}})
    profile_record(rec)
    entry=fill(rec,2,column="Joined")
    assert entry["imputation"]["excluded_estimates"] == 1
    assert rec["editor_df"].loc[2,"Joined"] == "03/01/2024"
    assert known_date_formats(rec)[("Joined",2)] == "DD/MM/YYYY"


def test_manual_correction_becomes_source_and_undo_restores_estimate_status():
    rec=record([10,None,None,30],"Amount")
    fill(rec,1,"constant","Amount",value=12)
    manual=apply_decision(rec,{"kind":"fix","body":{"revision":rec["editor_revision"],"column":"Amount","row_index":1,"scope":"cell","action":"replace","value":14}})
    profile_record(rec)
    assert ("Amount",1) not in estimated_cells(rec)
    replay_without(rec,manual["id"])
    assert ("Amount",1) in estimated_cells(rec)
    fill(rec,2,column="Amount")
    assert rec["editor_df"].loc[2,"Amount"] == 20


def test_group_failure_does_not_block_valid_group_and_cell_scope_ignores_other_groups():
    df=pd.DataFrame({"Entity":["A"]*3+["B"]*3,"Birth_Date":["2024-01-01",None,"2024-01-05","2024-02-15",None,"2024-99-99"]})
    result,audit=impute_missing_values(df,"Birth_Date","group_median",{"group_by":["Entity"]})
    assert result.loc[1,"Birth_Date"] == "2024-01-03" and result.loc[4,"Birth_Date"] is None
    assert audit["imputed_count"] == 1 and len(audit["failures"]) == 1 and "spreadsheet row 7" in audit["failures"][0]["reason"]
    selected,detail=propose(df,EditorRequest(revision=0,column="Birth_Date",row_index=1,scope="cell",action="impute_missing_values",parameters={"method":"group_median","group_by":["Entity"]}))
    assert selected.loc[1,"Birth_Date"] == "2024-01-03" and not detail["imputation"]["failures"]


@pytest.mark.parametrize("policy,expected",[("floor","2024-01-02"),("nearest","2024-01-03"),("ceil","2024-01-03")])
def test_date_rounding_is_explicit_and_recorded(policy,expected):
    result,audit=impute_missing_values(pd.DataFrame({"Birth_Date":["2024-01-01",None,"2024-01-04"]}),"Birth_Date","median",{"date_rounding":policy})
    assert result.loc[1,"Birth_Date"] == expected and audit["date_rounding"] == policy


def test_grouped_date_format_provenance_tracks_each_written_cell():
    rec={"editor_df":pd.DataFrame({"Entity":["A"]*3+["B"]*3,"Birth_Date":["13/01/2024",None,"17/01/2024","2024-02-13",None,"2024-02-17"]}),"editor_revision":0,"editor_changes":[]}
    ensure_workflow(rec);profile_record(rec)
    # These distinct formats are intentional and unambiguous. Review that finding
    # explicitly before testing each group's preserved imputation output format.
    apply_decision(rec,{"kind":"ignore","column":"Birth_Date","issue":"date_format","reason":"Reviewed distinct source formats; dates have unambiguous meanings."})
    apply_decision(rec,{"kind":"fix","body":{"revision":rec["editor_revision"],"column":"Birth_Date","row_index":1,"scope":"column","action":"impute_missing_values","parameters":{"method":"group_median","group_by":["Entity"]}}})
    assert known_date_formats(rec)[("Birth_Date",1)] == "DD/MM/YYYY"
    assert known_date_formats(rec)[("Birth_Date",4)] == "YYYY-MM-DD"

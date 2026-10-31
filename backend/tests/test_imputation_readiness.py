"""Missing-value filling is available only after other current column issues are resolved."""
import copy
import io
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.imputation_readiness import column_readiness, ensure_imputation_ready, readiness_from_annotations
from app.core.workflow import apply_decision, apply_recipe, ensure_workflow, profile_record, replay_without
from app.core.quality_tools import review as quality_review
from app.main import app, rate, store


def record(values=None, **extra):
    values = [10, None, "bad", 30] if values is None else values
    df = pd.DataFrame({"Key": [f"R{index}" for index in range(len(values))], "Amount": values, **extra})
    result = {"df": df.copy(deep=True), "editor_df": df, "editor_revision": 0,
              "editor_changes": [], "missing_marker_review_version": 1,
              "column_rules": {"Amount": {"type": "numeric"}}}
    ensure_workflow(result)
    profile_record(result)
    return result


def fix(rec, action="impute_missing_values", column="Amount", row=1, scope="column", value=None, **parameters):
    if action == "impute_missing_values" and parameters.get("method") == "constant":
        parameters["value"] = value
    return {"kind": "fix", "body": {"revision": rec["editor_revision"], "column": column,
            "row_index": row, "scope": scope, "action": action, "value": value, "parameters": parameters}}


def test_readiness_profile_uses_live_annotations_with_precise_cell_and_reason():
    rec = record()
    readiness = next(column for column in rec["editor_profile"]["columns"] if column["column_name"] == "Amount")["imputation_readiness"]
    assert not readiness["ready"]
    assert readiness["blocking_count"] > 0
    assert any(issue["kind"] == "rule_type" and issue["example_rows"] == [4] for issue in readiness["blocking_issues"])
    assert "Column 'Amount'" in readiness["message"] and "B4 (spreadsheet row 4)" in readiness["message"]
    with pytest.raises(ValueError, match="resolve other issues"):
        ensure_imputation_ready(rec, "Amount")


def test_old_schema_cannot_reuse_a_clean_annotation_cache():
    rec = record()
    rec["analysis_schema_version"] = 6
    rec["workflow_annotations"] = {"Key": {}, "Amount": {1: [{"kind": "missing"}]}}
    assert not column_readiness(rec, "Amount")["ready"]
    assert rec["analysis_schema_version"] == 8


@pytest.mark.parametrize("method", ["mean", "median", "mode", "constant", "forward_fill", "backward_fill",
                                      "linear_interpolation", "group_mean", "group_median", "group_mode",
                                      "group_forward_fill", "group_backward_fill", "date_sequence"])
def test_all_workflow_imputation_methods_block_before_computing(method):
    rec = record(Group=["A"] * 4, Order=[1, 2, 3, 4])
    parameters = {"method": method, "confirmed": True}
    if method == "constant":
        parameters["value"] = 9
    if method.startswith("group_"):
        parameters["group_by"] = ["Group"]
    if method in ("forward_fill", "backward_fill", "linear_interpolation", "group_forward_fill", "group_backward_fill", "date_sequence"):
        parameters.update(order_by="Order", single_entity=True)
    before = rec["editor_df"].copy(deep=True)
    with pytest.raises(ValueError, match="Column 'Amount'.*resolve other issues"):
        apply_decision(rec, fix(rec, **parameters))
    pd.testing.assert_frame_equal(rec["editor_df"], before)
    assert rec["editor_revision"] == 0 and not rec["workflow_steps"]


@pytest.mark.parametrize("kind", ["whitespace", "capitalization", "invalid_date", "ambiguous_date", "date_format",
    "data_format", "invalid_data_format", "type", "odd_value", "time", "invalid_time", "duration", "invalid_duration",
    "missing_marker", "duplicate", "outlier", "cross_column", "rule_negative", "rule_range", "rule_type"])
def test_every_nonmissing_live_issue_blocks_even_when_not_a_hard_error(kind):
    rec = record([10, None, 30])
    rec["workflow_annotations"]["Amount"] = {0: [{"kind": kind, "classification": "review"}], 1: [{"kind": "missing"}]}
    readiness = readiness_from_annotations(rec, "Amount")
    assert not readiness["ready"]
    assert readiness["blocking_issues"] == [{"kind": kind, "label": readiness["blocking_issues"][0]["label"], "count": 1, "example_rows": [2]}]


def test_required_actual_empty_is_not_a_blocker_but_required_on_marker_text_is():
    rec = record([10, None, 30])
    apply_decision(rec, {"kind": "rules", "column": "Amount", "settings": {"type": "numeric", "required": True}})
    assert column_readiness(rec, "Amount")["ready"]
    apply_decision(rec, fix(rec, method="median"))
    assert rec["editor_df"].at[1, "Amount"] == 20
    rec["editor_df"].at[1, "Amount"] = "NA"
    rec["workflow_annotations"]["Amount"] = {1: [{"kind": "rule_required"}]}
    assert not readiness_from_annotations(rec, "Amount")["ready"]


def test_fix_invalid_then_fill_refreshes_dirty_flags_and_preserve_is_always_allowed():
    rec = record()
    apply_decision(rec, fix(rec, method="preserve"))
    assert rec["editor_df"].at[2, "Amount"] == "bad"
    clear = apply_decision(rec, fix(rec, action="replace", row=2, scope="cell", value=None))
    assert "imputation_readiness_policy" not in rec["workflow_steps"][-1]
    assert column_readiness(rec, "Amount")["ready"]
    apply_decision(rec, fix(rec, method="median"))
    assert rec["editor_df"]["Amount"].tolist() == [10, 20, 20, 30]
    assert rec["workflow_steps"][-1]["imputation_readiness_policy"] == 1
    with pytest.raises(ValueError, match="Cannot undo safely.*later step depends"):
        replay_without(copy.deepcopy(rec), clear["id"])


def test_manual_filling_cannot_bypass_the_gate_but_correcting_nonempty_values_can():
    rec = record()
    with pytest.raises(ValueError, match="Column 'Amount'.*B4"):
        apply_decision(rec, fix(rec, action="replace", scope="cell", value=15))
    apply_decision(rec, fix(rec, action="replace", row=2, scope="cell", value=25))
    assert column_readiness(rec, "Amount")["ready"]
    apply_decision(rec, fix(rec, action="replace", scope="cell", value=15))
    assert rec["editor_df"].at[1, "Amount"] == 15
    assert rec["workflow_steps"][-1]["imputation_readiness_policy"] == 1


def test_new_manual_fill_replay_requires_its_earlier_cleanup():
    rec = record([" 10 ", None, "30"])
    cleanup = apply_decision(rec, fix(rec, action="trim_whitespace", row=0))
    apply_decision(rec, fix(rec, action="replace", scope="cell", value=15))
    assert rec["workflow_steps"][-1]["imputation_readiness_policy"] == 1
    with pytest.raises(ValueError, match="Cannot undo safely.*later step depends"):
        replay_without(copy.deepcopy(rec), cleanup["id"])


def test_explicit_accepted_findings_are_respected_and_other_columns_do_not_block():
    rec = record(Other=[" mixed ", "CASE", "case", "different"])
    apply_decision(rec, {"kind": "ignore", "column": "Amount", "row_index": 2, "issue": "*", "value": "bad"})
    assert column_readiness(rec, "Amount")["ready"]
    # A constant can be used after the user has explicitly accepted the observed text.
    apply_decision(rec, fix(rec, method="constant", value=12))
    assert rec["editor_df"].at[1, "Amount"] == 12
    assert not column_readiness(rec, "Other")["ready"]


def test_clean_column_imputation_not_blocked_by_unrelated_column_issues():
    rec = record([10, None, 30], Other=[" Cairo ", "CAIRO", "Cairo"])
    assert column_readiness(rec, "Amount")["ready"]
    apply_decision(rec, fix(rec, method="median"))
    assert rec["editor_df"].at[1, "Amount"] == 20


def test_old_unmarked_filling_steps_can_replay_without_resetting_user_history():
    rec = record(Other=[" a ", "b", "c", "d"])
    unrelated = apply_decision(rec, fix(rec, action="trim_whitespace", column="Other", row=0))
    apply_decision(rec, fix(rec, action="replace", scope="cell", value=15), enforce_imputation_readiness=False)
    assert "imputation_readiness_policy" not in rec["workflow_steps"][-1]
    replay_without(rec, unrelated["id"])
    assert rec["editor_df"].at[1, "Amount"] == 15 and rec["editor_df"].at[2, "Amount"] == "bad"
    assert "imputation_readiness_policy" not in rec["workflow_steps"][-1]


def test_recipe_rechecks_after_each_cleanup_step_and_rejects_filling_first():
    # A whole-column cleanup can remove the issue before the later imputation.
    rec = record([" 10 ", None, "30"])
    recipe = {"version": 1, "name": "Clean then estimate", "source_columns": ["Key", "Amount"],
              "steps": [fix(rec, action="trim_whitespace", row=0), fix(rec, method="median")]}
    apply_recipe(rec, recipe)
    assert rec["editor_df"].at[1, "Amount"] == 20
    blocked = record([" 10 ", None, "30"])
    recipe["steps"].reverse()
    with pytest.raises(ValueError, match="resolve other issues"):
        apply_recipe(blocked, recipe)


@pytest.mark.parametrize("method", ["knn", "iterative"])
def test_model_review_and_apply_gate_before_model_computation(method):
    rec = record(Driver=[1, 2, 3, 4])
    settings = {"tool": "model_imputation", "method": method, "target": "Amount", "helpers": ["Driver"], "acknowledge": True}
    with pytest.raises(ValueError, match="Column 'Amount'.*resolve other issues"):
        quality_review(rec, settings)
    with pytest.raises(ValueError, match="Column 'Amount'.*resolve other issues"):
        apply_decision(rec, {"kind": "quality", "settings": settings})


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    rate.clear()
    return TestClient(app)


def upload(client, content):
    response = client.post("/api/files/upload", files={"file": ("readiness.csv", content, "text/csv")})
    assert response.status_code == 200, response.text
    fid = response.json()["file_id"]
    response = client.post(f"/api/files/{fid}/workflow/init")
    assert response.status_code == 200, response.text
    return fid, response.json()


def job(client, fid, revision=0, operation="decision", **kwargs):
    rate.clear()
    response = client.post(f"/api/files/{fid}/workflow/jobs", json={"revision": revision, "operation": operation, **kwargs})
    assert response.status_code == 202, response.text
    jid = response.json()["job_id"]
    for _ in range(1000):
        rate.clear()
        response = client.get(f"/api/workflow-jobs/{jid}")
        assert response.status_code == 200, response.text
        status = response.json()
        if status["status"] not in ("queued", "running"):
            return status
        time.sleep(.01)
    pytest.fail("Readiness job did not complete")


def test_automatic_skips_blocked_imputation_and_keeps_successful_other_steps(client):
    fid, initial = upload(client, b"Key,Amount,City\nR1,-10, cairo \nR2,,giza\nR3,30,alex\n")
    policy = job(client, fid, decision={"kind": "negative_policy", "column": "Amount", "settings": {"allow_negative": False}})
    assert policy["status"] == "completed", policy
    result = job(client, fid, revision=1, operation="automatic", answers={"missing": "median", "trim": True, "capitalization": "title"})
    assert result["status"] == "completed", result
    assert any("Column 'Amount'" in reason for reason in result["result"]["skipped"])
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][1][1] in (None, "")
    assert current["preview"]["rows"][0][2] == "Cairo"


def test_automatic_prior_cleanup_rechecks_readiness_before_filling(client):
    fid, initial = upload(client, b"Key,Amount\nR1, 10 \nR2,\nR3,30\n")
    assert not initial["profile"]["columns"][1]["imputation_readiness"]["ready"]
    result = job(client, fid, operation="automatic", answers={"missing": "median", "trim": True})
    assert result["status"] == "completed", result
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][1][1] == 20
    assert not any("Column 'Amount'" in reason for reason in result["result"]["skipped"])


def test_direct_workflow_jobs_and_manual_missing_replacement_cannot_bypass(client):
    fid, initial = upload(client, b"Key,Amount\nR1,10\nR2,\nR3,bad\nR4,30\n")
    rule = job(client, fid, decision={"kind": "rules", "column": "Amount", "settings": {"type": "numeric"}})
    assert rule["status"] == "completed", rule
    for action, parameters, value in [("impute_missing_values", {"method": "constant", "value": 15}, None), ("replace", {}, 15)]:
        result = job(client, fid, revision=1, decision={"kind": "fix", "body": {"revision": 1,
            "column": "Amount", "row_index": 1, "scope": "cell", "action": action,
            "parameters": parameters, "value": value}})
        assert result["status"] == "failed", result
        assert "Column 'Amount'" in result["error"] and "B4" in result["error"]
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["revision"] == 1 and current["preview"]["rows"] == initial["preview"]["rows"]


def test_plan_and_undo_apply_readiness_against_current_intermediate_sheet(client):
    fid, initial = upload(client, b"Key,Amount\nR1, 10 \nR2,\nR3,30\n")
    steps = [{"kind": "fix", "body": {"revision": 0, "column": "Amount", "row_index": 0,
              "scope": "column", "action": "trim_whitespace", "parameters": {}}},
             {"kind": "fix", "body": {"revision": 0, "column": "Amount", "row_index": 0,
              "scope": "column", "action": "impute_missing_values", "parameters": {"method": "median"}}}]
    result = job(client, fid, operation="plan_preview", steps=steps)
    assert result["status"] == "completed", result
    assert client.get(f"/api/files/{fid}/editor").json()["revision"] == 0
    result = job(client, fid, operation="plan", steps=steps)
    assert result["status"] == "completed", result
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][1][1] == 20
    blocked = job(client, fid, revision=current["revision"], operation="undo", step_id=current["changes"][0]["id"])
    assert blocked["status"] == "failed" and "Cannot undo safely" in blocked["error"], blocked
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"] == current["preview"]["rows"]

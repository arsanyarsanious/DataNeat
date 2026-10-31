"""Suggested corrections remain a read-only review until an owner applies a plan."""
import copy
import csv
import io
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app, rate, store
from app.core.profiler import profile_dataframe
from app.core.suggested_cleaning import suggested_cleaning
from app.core.workflow import apply_decision, ensure_workflow, known_date_formats, manual_acceptances, profile_record, recipe_from
from app.models.requests import EditorRequest


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear()
    rate.clear()
    return TestClient(app)


def upload(client, columns, rows):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(columns)
    writer.writerows(rows)
    response = client.post("/api/files/upload", files={"file": ("suggested.csv", stream.getvalue().encode(), "text/csv")})
    assert response.status_code == 200, response.text
    file_id = response.json()["file_id"]
    response = client.post(f"/api/files/{file_id}/workflow/init")
    assert response.status_code == 200, response.text
    return file_id, response.json()


def current(client, file_id):
    response = client.get(f"/api/files/{file_id}/editor?page_size=100")
    assert response.status_code == 200, response.text
    return response.json()


def stored(client, file_id):
    return store.get(file_id, client.cookies.get("dataneat_session"))


def start_job(client, file_id, operation, revision=None, **values):
    rate.clear()
    if revision is None:
        revision = current(client, file_id)["revision"]
    response = client.post(f"/api/files/{file_id}/workflow/jobs", json={"revision": revision, "operation": operation, **values})
    assert response.status_code == 202, response.text
    key = response.json()["job_id"]
    for _ in range(1000):
        rate.clear()
        status = client.get(f"/api/workflow-jobs/{key}")
        assert status.status_code == 200, status.text
        result = status.json()
        if result["status"] not in ("queued", "running"):
            return result
        time.sleep(.01)
    pytest.fail("Suggested cleaning job did not complete")


def completed(client, file_id, operation, **values):
    status = start_job(client, file_id, operation, **values)
    assert status["status"] == "completed", status
    return status["result"]


def suggested(client, file_id):
    response = client.get(f"/api/files/{file_id}/workflow/suggested")
    assert response.status_code == 200, response.text
    return response.json()


def record_for(data):
    frame = pd.DataFrame(data, dtype=object)
    record = {"editor_df": frame, "df": frame.copy(deep=True), "profile": profile_dataframe(frame), "editor_revision": 0, "editor_changes": [], "missing_marker_review_version": 1}
    ensure_workflow(record)
    profile_record(record)
    return record


def issue_columns_body(revision=0, column="Primary_Email", row=0, columns=None, kind="email", value="Not provided"):
    return {"revision": revision, "column": column, "row_index": row, "action": "replace", "scope": "issue_columns", "value": value, "parameters": {"columns": columns or ["Primary_Email", "Backup_Email"], "issue_kind": kind}}


def email_rows():
    return [["wrong-a", "wrong-b", "wrong-c"], ["valid@example.com", "valid2@example.com", "wrong-d"], ["wrong-e", "wrong-f", "ok@example.com"]]


def test_suggestions_group_columns_once_in_stable_order_with_duplicates_last():
    record = record_for({"Name": [" Alice ", "Bob", " Alice "], "City": [" Cairo ", "Giza", " Cairo "], "Active": ["yes", "false", "yes"]})
    before = copy.deepcopy(record)
    first = suggested_cleaning(record)
    second = suggested_cleaning(record)
    assert first == second
    assert first["revision"] == 0
    assert first["source_columns"] == ["Name", "City", "Active"]
    assert [group["id"] for group in first["groups"]] == ["whitespace", "boolean", "duplicate"]
    whitespace = first["groups"][0]
    assert whitespace["columns"] == ["Name", "City"]
    assert whitespace["count"] == 4
    assert [step["body"]["column"] for step in whitespace["steps"]] == ["Name", "City"]
    assert all(step["body"]["scope"] == "column" for group in first["groups"] for step in group["steps"])
    assert first["groups"][-1]["safety"] == "destructive"
    assert first["groups"][-1]["steps"][0]["body"]["action"] == "remove_duplicates"
    pd.testing.assert_frame_equal(record["editor_df"], before["editor_df"])
    assert record["editor_revision"] == before["editor_revision"]
    assert record["workflow_steps"] == before["workflow_steps"]
    assert record["complete_changes"] == before["complete_changes"]


def test_suggestions_defer_identifiers_accepted_columns_and_unresolved_labels():
    record = record_for({"Customer_ID": [" 001 ", "002", "003"], "Edited": [" Alice ", "Bob", "Charlie"], "Labels": ["NA", " Cairo ", "Giza"], "Eligible": [" Cairo ", "Giza", "Alexandria"]})
    apply_decision(record, {"kind": "fix", "body": {"revision": 0, "column": "Edited", "row_index": 1, "action": "replace", "value": "Approved by user"}})
    profile_record(record)
    result = suggested_cleaning(record)
    proposed_columns = {column for group in result["groups"] for column in group["columns"]}
    assert proposed_columns == {"Eligible"}
    assert result["protected_columns"] == ["Edited"]
    assert any(item["label"].startswith("Customer_ID:") and "Identifiers" in item["reason"] for item in result["deferred"])
    assert any(item["label"].startswith("Edited:") and "User-entered" in item["reason"] for item in result["deferred"])
    assert any(item["label"].startswith("Labels:") and "missing-value labels" in item["reason"] for item in result["deferred"])
    assert record["editor_df"].at[0, "Labels"] == "NA"
    assert record["editor_df"].at[0, "Customer_ID"] == " 001 "


def test_capitalization_suggestions_only_target_text_despite_stray_case_statistics():
    record = record_for({
        "Active": ["TRUE", "false", "Yes"],
        "Date": ["2024-01-13", "2024-01-14", "2024-01-15"],
        "Customer_ID": ["abc", "ABC", "Def"],
        "City": ["cairo", "Cairo", "CAIRO"],
    })
    detected = {column["column_name"]: column["detected_type"] for column in record["editor_profile"]["columns"]}
    assert detected["Active"] == "boolean"
    assert detected["Date"] == "date"
    assert detected["Customer_ID"] == "identifier"
    assert detected["City"] in ("text", "category", "categorical")
    # Mixed case statistics can survive beside a more specific inferred type.
    for column in record["editor_profile"]["columns"]:
        column["issues"] = [issue for issue in column["issues"] if issue["issue"] != "case_inconsistency"]
        column["issues"].append({"issue": "case_inconsistency", "column": column["column_name"], "count": 3, "examples": []})
    result = suggested_cleaning(record)
    capitalization = next(group for group in result["groups"] if group["id"] == "capitalization")
    assert capitalization["columns"] == ["City"]
    assert [step["body"]["column"] for step in capitalization["steps"]] == ["City"]
    assert any(group["id"] == "boolean" and group["columns"] == ["Active"] for group in result["groups"])
    assert {item["label"].split(":", 1)[0] for item in result["deferred"] if item["kind"] == "case_inconsistency"} == {"Active", "Date", "Customer_ID"}


def test_suggestions_do_not_guess_invalid_values_missing_measurements_or_date_interpretation():
    record = record_for({"Measure": ["10", None, "30", "40"], "Email": ["bad", "a@example.com", "b@example.com", "c@example.com"], "Date": ["2024-01-13", "2024-01-14", "2024-99-88", "01/02/2024"]})
    result = suggested_cleaning(record)
    actions = [step["body"]["action"] for group in result["groups"] for step in group["steps"]]
    assert "replace" not in actions
    assert "resolve_invalid_dates" not in actions
    assert "impute_missing_values" not in actions
    for group in result["groups"]:
        for step in group["steps"]:
            if step["body"]["action"] == "normalize_dates":
                assert step["body"]["parameters"]["interpretation"] == "preserve"
    deferred = {item["kind"] for item in result["deferred"]}
    assert {"missing_values", "invalid_email", "invalid_dates", "ambiguous_dates"} <= deferred
    assert record["editor_df"].at[1, "Measure"] is None
    assert record["editor_df"].at[2, "Date"] == "2024-99-88"


def test_suggestions_bound_whole_column_actions_to_100_including_duplicate_removal():
    record = record_for({f"Text_{index}": [" value ", " value "] for index in range(120)})
    result = suggested_cleaning(record)
    steps = [step for group in result["groups"] for step in group["steps"]]
    assert len(steps) == 100
    assert result["groups"][-1]["id"] == "duplicate"
    assert len(result["groups"][0]["steps"]) == 99
    assert len({step["body"]["column"] for step in result["groups"][0]["steps"]}) == 99
    assert any("100 actions" in item["reason"] for item in result["deferred"])
    assert record["editor_revision"] == 0


def test_suggested_endpoint_is_owner_scoped_current_revision_and_read_only(client):
    file_id, initial = upload(client, ["Name", "City"], [[" Alice ", " Cairo "], ["Bob", "Giza"]])
    before = stored(client, file_id)
    response = suggested(client, file_id)
    assert response["revision"] == initial["revision"]
    assert TestClient(app).get(f"/api/files/{file_id}/workflow/suggested").status_code == 404
    after = stored(client, file_id)
    pd.testing.assert_frame_equal(after["editor_df"], before["editor_df"])
    assert after["editor_revision"] == before["editor_revision"]
    assert after["editor_changes"] == before["editor_changes"]
    assert after["workflow_steps"] == before["workflow_steps"]
    assert after["complete_changes"] == before["complete_changes"]
    completed(client, file_id, "decision", decision={"kind": "fix", "body": {"revision": 0, "column": "Name", "row_index": 1, "action": "replace", "value": "Robert"}})
    assert suggested(client, file_id)["revision"] == 1
    assert suggested(client, file_id)["protected_columns"] == ["Name"]
    stale = client.post(f"/api/files/{file_id}/workflow/jobs", json={"revision": 0, "operation": "plan", "steps": response["groups"][0]["steps"]})
    assert stale.status_code == 409
    assert current(client, file_id)["revision"] == 1


def test_combined_suggestion_preview_apply_metrics_and_stepwise_undo(client):
    file_id, initial = upload(client, ["Name", "City"], [[" Alice ", " Cairo "], ["Bob", "Giza"], [" Alice ", " Cairo "]])
    groups = suggested(client, file_id)["groups"]
    assert [group["id"] for group in groups] == ["whitespace", "duplicate"]
    steps = [step for group in groups for step in group["steps"]]
    preview = completed(client, file_id, "plan_preview", steps=steps)
    assert preview["changed_cells"] == 4
    assert preview["removed_rows"] == 1
    assert current(client, file_id)["preview"]["rows"] == initial["preview"]["rows"]
    assert not current(client, file_id)["changes"]
    applied = completed(client, file_id, "plan", steps=steps)
    assert applied["changed_cells"] == 4 and applied["removed_rows"] == 1
    changed = current(client, file_id)
    assert changed["preview"]["rows"] == [["Alice", "Cairo"], ["Bob", "Giza"]]
    assert len(changed["changes"]) == 3
    assert [step["column"] for step in changed["changes"][:2]] == ["Name", "City"]
    for _ in range(3):
        completed(client, file_id, "undo", step_id=current(client, file_id)["changes"][-1]["id"])
    restored = current(client, file_id)
    assert restored["preview"]["rows"] == initial["preview"]["rows"]
    assert not restored["changes"]
    assert not stored(client, file_id)["complete_changes"]


def test_suggested_dates_preserve_confirmed_day_first_provenance(client):
    file_id, _ = upload(client, ["Date", "Row"], [["07/08/2024", "a"], ["2024-07-13", "b"], ["2024-07-14", "c"]])
    completed(client, file_id, "decision", decision={"kind": "fix", "body": {"revision": 0, "column": "Date", "row_index": 0, "scope": "cell", "action": "normalize_dates", "parameters": {"interpretation": "day_first", "output_format": "DD/MM/YYYY"}}})
    before = stored(client, file_id)
    assert known_date_formats(before)[("Date", 0)] == "DD/MM/YYYY"
    group = next(group for group in suggested(client, file_id)["groups"] if group["id"] == "date_format")
    preview = completed(client, file_id, "plan_preview", steps=group["steps"])
    examples = [example for step in preview["operations"] for example in step["examples"]]
    assert any(item["row_index"] == 0 and item["after"] == "2024-08-07" for item in examples)
    assert current(client, file_id)["preview"]["rows"][0][0] == "07/08/2024"
    assert known_date_formats(stored(client, file_id)) == known_date_formats(before)
    completed(client, file_id, "plan", steps=group["steps"])
    changed = current(client, file_id)
    assert changed["preview"]["rows"][0][0] == "2024-08-07"
    completed(client, file_id, "undo", step_id=changed["changes"][-1]["id"])
    assert current(client, file_id)["preview"]["rows"][0][0] == "07/08/2024"
    assert known_date_formats(stored(client, file_id))[("Date", 0)] == "DD/MM/YYYY"


def test_combined_plan_failure_does_not_commit_an_earlier_valid_correction(client):
    file_id, initial = upload(client, ["Name", "City"], [[" Alice ", " Cairo "], ["Bob", "Giza"]])
    steps = suggested(client, file_id)["groups"][0]["steps"]
    steps[1]["body"]["column"] = "Column removed since review"
    status = start_job(client, file_id, "plan", steps=steps)
    assert status["status"] == "failed", status
    after = current(client, file_id)
    assert after["revision"] == 0
    assert after["preview"]["rows"] == initial["preview"]["rows"]
    assert not after["changes"]
    assert not stored(client, file_id)["complete_changes"]


def test_issue_columns_only_changes_flagged_cells_in_explicit_columns_with_acceptance_and_undo(client):
    file_id, initial = upload(client, ["Primary_Email", "Backup_Email", "Unselected_Email"], email_rows())
    body = issue_columns_body()
    preview = completed(client, file_id, "preview", decision={"kind": "fix", "body": body})
    assert preview["proposal"]["changed_cells"] == 4
    assert current(client, file_id)["preview"]["rows"] == initial["preview"]["rows"]
    assert not manual_acceptances(stored(client, file_id))
    completed(client, file_id, "decision", decision={"kind": "fix", "body": body})
    changed = current(client, file_id)
    assert changed["preview"]["rows"] == [["Not provided", "Not provided", "wrong-c"], ["valid@example.com", "valid2@example.com", "wrong-d"], ["Not provided", "Not provided", "ok@example.com"]]
    accepted = manual_acceptances(stored(client, file_id))
    assert {(item["column"], item["row_index"]) for item in accepted} == {("Primary_Email", 0), ("Primary_Email", 2), ("Backup_Email", 0), ("Backup_Email", 2)}
    assert all(item["value"] == "Not provided" for item in accepted)
    assert not changed["preview"]["cell_issues"][0][0]
    assert any(flag["kind"] == "email" for flag in changed["preview"]["cell_issues"][0][2])
    assert changed["changes"][-1]["scope"] == "issue_columns"
    assert changed["changes"][-1]["column"] == "Primary_Email, Backup_Email"
    assert changed["changes"][-1]["decision"]["body"]["column"] == "Primary_Email"
    assert not recipe_from(stored(client, file_id))["steps"]
    audit = stored(client, file_id)["complete_changes"]
    assert {(entry["column"], entry["row_index"]) for entry in audit} == {(item["column"], item["row_index"]) for item in accepted}
    completed(client, file_id, "undo", step_id=changed["changes"][-1]["id"])
    restored = current(client, file_id)
    assert restored["preview"]["rows"] == initial["preview"]["rows"]
    assert any(flag["kind"] == "email" for flag in restored["preview"]["cell_issues"][0][0])
    assert not manual_acceptances(stored(client, file_id))


def test_issue_columns_replay_after_undo_uses_restored_flags_and_retains_acceptances(client):
    rows = [row + [" extra space "] for row in email_rows()]
    file_id, _ = upload(client, ["Primary_Email", "Backup_Email", "Unselected_Email", "Notes"], rows)
    completed(client, file_id, "decision", decision={"kind": "fix", "body": {"revision": 0, "column": "Notes", "row_index": 0, "scope": "column", "action": "trim_whitespace"}})
    trimmed = current(client, file_id)
    trim_id = trimmed["changes"][-1]["id"]
    completed(client, file_id, "decision", decision={"kind": "fix", "body": issue_columns_body(revision=trimmed["revision"])})
    # Remove an earlier unrelated step, so the multi-column issue correction must replay.
    completed(client, file_id, "undo", step_id=trim_id)
    replayed = current(client, file_id)
    assert len(replayed["changes"]) == 1
    assert replayed["changes"][0]["scope"] == "issue_columns"
    assert replayed["changes"][0]["column"] == "Primary_Email, Backup_Email"
    assert replayed["preview"]["rows"][0] == ["Not provided", "Not provided", "wrong-c", " extra space "]
    assert replayed["preview"]["rows"][1] == rows[1]
    assert len(manual_acceptances(stored(client, file_id))) == 4
    assert not recipe_from(stored(client, file_id))["steps"]


@pytest.mark.parametrize("failure", ["selected_valid", "unknown_column", "identifier"])
def test_issue_columns_failures_are_atomic_even_after_a_prior_column_would_change(client, failure):
    file_id, initial = upload(client, ["Primary_Email", "Backup_Email", "Customer_ID"], [[a, b, f"00{index}"] for index, (a, b, _) in enumerate(email_rows())])
    if failure == "selected_valid":
        # Backup has flagged cells, but the selected Primary cell is valid.
        body = issue_columns_body(row=1, columns=["Backup_Email", "Primary_Email"])
    elif failure == "unknown_column":
        body = issue_columns_body(columns=["Primary_Email", "Missing"])
    else:
        body = issue_columns_body(columns=["Primary_Email", "Customer_ID"])
    status = start_job(client, file_id, "decision", decision={"kind": "fix", "body": body})
    assert status["status"] == "failed", status
    assert ("selected cell" if failure == "selected_valid" else "no longer exists" if failure == "unknown_column" else "Identifiers") in status["error"]
    unchanged = current(client, file_id)
    assert unchanged["revision"] == initial["revision"]
    assert unchanged["preview"]["rows"] == initial["preview"]["rows"]
    assert not unchanged["changes"]
    assert not stored(client, file_id)["complete_changes"]


def test_issue_columns_declared_identifier_is_protected_even_if_not_inferred(client):
    file_id, _ = upload(client, ["Primary_Email", "Backup_Email", "Ordinary"], email_rows())
    completed(client, file_id, "decision", decision={"kind": "rules", "column": "Ordinary", "settings": {"type": "identifier"}})
    before = current(client, file_id)
    body = issue_columns_body(revision=before["revision"], columns=["Primary_Email", "Ordinary"])
    status = start_job(client, file_id, "decision", decision={"kind": "fix", "body": body})
    assert status["status"] == "failed" and "Identifiers" in status["error"]
    after = current(client, file_id)
    assert after["revision"] == before["revision"]
    assert after["preview"]["rows"] == before["preview"]["rows"]


@pytest.mark.parametrize("changes", [
    {"action": "trim_whitespace"},
    {"parameters": {"columns": [], "issue_kind": "email"}},
    {"parameters": {"columns": ["Primary_Email", "Primary_Email"], "issue_kind": "email"}},
    {"parameters": {"columns": ["Backup_Email"], "issue_kind": "email"}},
    {"parameters": {"columns": ["Primary_Email", 1], "issue_kind": "email"}},
    {"parameters": {"columns": ["Primary_Email"], "issue_kind": "bad kind"}},
    {"parameters": {"columns": ["Primary_Email"], "issue_kind": ""}},
])
def test_issue_columns_request_rejects_invalid_action_column_lists_and_issue_kinds(changes):
    with pytest.raises(ValidationError):
        EditorRequest(**{**issue_columns_body(), **changes})

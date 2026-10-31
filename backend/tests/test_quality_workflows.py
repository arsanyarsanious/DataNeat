"""Reviewed tools use the real owner-scoped jobs, audit, flags and undo workflow."""
import csv
import io
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app, rate, store
from app.core.workflow import estimated_cells, known_date_formats, manual_acceptances


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
    response = client.post("/api/files/upload", files={"file": ("quality.csv", stream.getvalue().encode(), "text/csv")})
    assert response.status_code == 200, response.text
    fid = response.json()["file_id"]
    response = client.post(f"/api/files/{fid}/workflow/init")
    assert response.status_code == 200, response.text
    return fid, response.json()


def current(client, fid):
    response = client.get(f"/api/files/{fid}/editor?page_size=100")
    assert response.status_code == 200, response.text
    return response.json()


def stored(client, fid):
    return store.get(fid, client.cookies.get("dataneat_session"))


def job(client, fid, operation, revision=None, **body):
    rate.clear()
    revision = current(client, fid)["revision"] if revision is None else revision
    response = client.post(f"/api/files/{fid}/workflow/jobs", json={"revision": revision, "operation": operation, **body})
    assert response.status_code == 202, response.text
    key = response.json()["job_id"]
    for _ in range(1000):
        rate.clear()
        response = client.get(f"/api/workflow-jobs/{key}")
        assert response.status_code == 200, response.text
        status = response.json()
        if status["status"] not in ("queued", "running"):
            assert status["status"] == "completed", status
            return status["result"]
        time.sleep(.01)
    pytest.fail("Quality tool job did not complete")


def quality(client, fid, tool, **settings):
    return job(client, fid, "decision", decision={"kind": "quality", "settings": {"tool": tool, **settings}})


def undo(client, fid, step=None):
    step = step or current(client, fid)["changes"][-1]["id"]
    job(client, fid, "undo", step_id=step)
    return current(client, fid)


def flags(state, column, row, kind):
    offset = state["preview"]["columns"].index(column)
    return [item for item in state["preview"]["cell_issues"][row][offset] if item["kind"] == kind]


def cross_rule():
    return {"id": "check-total", "label": "Quantity times price", "kind": "arithmetic", "target": "Total", "left": "Quantity", "right": "Price", "arithmetic": "multiply"}


def replace(client, fid, column, row, value):
    revision = current(client, fid)["revision"]
    return job(client, fid, "decision", decision={"kind": "fix", "body": {"revision": revision, "column": column, "row_index": row, "action": "replace", "scope": "cell", "value": value}})


def test_cross_rules_refresh_after_operand_edits_recalculate_audit_and_undo(client):
    fid, initial = upload(client, ["Quantity", "Price", "Total"], [[2, 10, 20], [3, 20, 50]])
    quality(client, fid, "cross_column", action="save_rules", rules=[cross_rule()])
    saved = current(client, fid)
    assert saved["revision"] == 1
    assert saved["preview"]["rows"] == initial["preview"]["rows"]
    assert flags(saved, "Total", 1, "cross_column")
    assert not flags(saved, "Total", 0, "cross_column")
    # A clean target's cached flags must refresh when a different column changes.
    replace(client, fid, "Quantity", 0, "4")
    changed = current(client, fid)
    assert flags(changed, "Total", 0, "cross_column")
    quality(client, fid, "cross_column", action="recalculate", rule_id="check-total")
    recalculated = current(client, fid)
    assert [row[2] for row in recalculated["preview"]["rows"]] == ["40", "60"]
    assert not any(flags(recalculated, "Total", row, "cross_column") for row in (0, 1))
    assert recalculated["changes"][-1]["action"] == "cross_column_recalculate"
    assert recalculated["changes"][-1]["changed_cells"] == 2
    changes = stored(client, fid)["complete_changes"]
    assert {(item["column"], item["spreadsheet_row"], item["before"], item["after"]) for item in changes if item["action"] == "cross_column_recalculate"} == {("Total", 2, "20", "40"), ("Total", 3, "50", "60")}
    restored = undo(client, fid)
    assert [row[2] for row in restored["preview"]["rows"]] == ["20", "50"]
    assert flags(restored, "Total", 0, "cross_column")
    undo(client, fid)  # Remove operand edit before removing the saved rule.
    removed_rule = undo(client, fid)
    assert not stored(client, fid).get("cross_column_rules")
    assert not any(flags(removed_rule, "Total", row, "cross_column") for row in (0, 1))


def test_cross_rule_references_follow_rename_and_undo(client):
    fid, _ = upload(client, ["Quantity", "Price", "Total"], [[2, 10, 1], [3, 20, 2]])
    quality(client, fid, "cross_column", action="save_rules", rules=[cross_rule()])
    job(client, fid, "decision", decision={"kind": "rename", "column": "Quantity", "settings": {"name": "Count"}})
    assert stored(client, fid)["cross_column_rules"][0]["left"] == "Count"
    assert flags(current(client, fid), "Total", 0, "cross_column")
    quality(client, fid, "cross_column", action="recalculate", rule_id="check-total")
    assert current(client, fid)["preview"]["rows"][0] == ["2", "10", "20"]
    undo(client, fid)
    restored = undo(client, fid)
    assert "Quantity" in restored["preview"]["columns"]
    assert stored(client, fid)["cross_column_rules"][0]["left"] == "Quantity"


def test_quality_analysis_and_preview_are_read_only_and_stale_revision_rejected(client):
    fid, initial = upload(client, ["Quantity", "Price", "Total"], [[2, 10, 1], [3, 20, 2]])
    settings = {"tool": "cross_column", "action": "save_rules", "rules": [cross_rule()]}
    analyzed = job(client, fid, "quality_review", quality=settings)
    assert analyzed["finding_count"] == 2
    assert current(client, fid)["revision"] == initial["revision"]
    assert not stored(client, fid).get("cross_column_rules")
    preview = job(client, fid, "preview", decision={"kind": "quality", "settings": settings})
    assert preview["proposal"]["changed_cells"] == 0
    assert preview["quality"]["finding_count"] == 2
    assert not stored(client, fid).get("cross_column_rules")
    quality(client, fid, "cross_column", action="save_rules", rules=[cross_rule()])
    response = client.post(f"/api/files/{fid}/workflow/jobs", json={"revision": 0, "operation": "decision", "decision": {"kind": "quality", "settings": settings}})
    assert response.status_code == 409
    assert current(client, fid)["revision"] == 1


@pytest.mark.parametrize("action", ["cap", "clear", "keep"])
def test_outlier_flags_actions_audit_and_undo(client, action):
    fid, initial = upload(client, ["Reading", "Group"], [[value, "A"] for value in [10, 11, 12, 13, 14, 15, 1000]])
    config = {"column": "Reading", "method": "iqr", "multiplier": 1.5, "group_by": []}
    analyzed = job(client, fid, "quality_review", quality={"tool": "outliers", "action": "review", **config})
    assert analyzed["count"] == 1
    assert current(client, fid)["revision"] == 0
    quality(client, fid, "outliers", action="save", **config)
    saved = current(client, fid)
    assert flags(saved, "Reading", 6, "outlier")
    quality(client, fid, "outliers", action=action, confirmed=True, **config)
    changed = current(client, fid)
    value = changed["preview"]["rows"][6][0]
    if action == "clear":
        assert value is None
    elif action == "cap":
        assert 15 < value < 1000
    else:
        assert value == "1000"
        assert stored(client, fid)["outlier_acceptances"]
        assert changed["changes"][-1]["changed_cells"] == 0
    assert not flags(changed, "Reading", 6, "outlier")
    restored = undo(client, fid)
    assert restored["preview"]["rows"] == initial["preview"]["rows"]
    assert flags(restored, "Reading", 6, "outlier")
    unsaved = undo(client, fid)
    assert not stored(client, fid).get("outlier_rules")
    assert not flags(unsaved, "Reading", 6, "outlier")


@pytest.mark.parametrize("method", ["knn", "iterative"])
def test_models_exclude_prior_estimates_mark_new_estimates_and_undo(client, method):
    rows = [[index, None if index in (6, 13) else index * 2 + 5] for index in range(1, 15)]
    fid, initial = upload(client, ["Driver", "Measurement"], rows)
    job(client, fid, "decision", decision={"kind": "fix", "body": {"revision": 0, "column": "Measurement", "row_index": 5, "scope": "cell", "action": "impute_missing_values", "parameters": {"method": "median"}}})
    previous = current(client, fid)
    assert previous["preview"]["is_imputed"][5][1]
    assert previous["preview"]["rows"][12][1] in (None, "")
    config = {"tool": "model_imputation", "target": "Measurement", "helpers": ["Driver"], "method": method, "neighbors": 3, "max_iter": 10, "acknowledge": True}
    analyzed = job(client, fid, "quality_review", quality=config)
    assert analyzed["excluded_estimates_by_column"]["Measurement"] == 1
    assert analyzed["donor_count"] == 12
    assert analyzed["filled_count"] == 1
    assert analyzed["validation"]["status"] == "available"
    assert current(client, fid)["revision"] == previous["revision"]
    job(client, fid, "decision", decision={"kind": "quality", "settings": config})
    changed = current(client, fid)
    assert changed["preview"]["rows"][12][1] is not None
    assert changed["preview"]["is_imputed"][12][1]
    assert changed["preview"]["is_imputed"][5][1]
    assert changed["changes"][-1]["action"] == "impute_missing_values"
    assert changed["changes"][-1]["imputation"]["method"] == method
    assert changed["changes"][-1]["changed_cells"] == 1
    assert [row[0] for row in changed["preview"]["rows"]] == [row[0] for row in initial["preview"]["rows"]]
    restored = undo(client, fid)
    assert restored["preview"]["rows"] == previous["preview"]["rows"]
    assert restored["preview"]["is_imputed"][5][1]
    assert not restored["preview"]["is_imputed"][12][1]


def records():
    return [["001", "Jon Smith", "Cairo", ""], ["002", "John Smith", "Cairo", "01234567890"], ["003", "Mary Jones", "Alexandria", "01123456789"]]


def test_record_merge_full_audit_removed_rows_and_undo(client):
    fid, initial = upload(client, ["Customer_ID", "Name", "City", "Phone"], records())
    base = {"columns": ["Name", "City"], "threshold": .8, "block_by": ""}
    analyzed = job(client, fid, "quality_review", quality={"tool": "record_matching", **base})
    assert any({pair["left_row"], pair["right_row"]} == {0, 1} for pair in analyzed["pairs"])
    settings = {"tool": "record_matching", "action": "merge", **base, "left_row": 0, "right_row": 1, "keep_row": 0, "choices": {"Customer_ID": "left", "Name": "right"}, "confirmed": True}
    preview = job(client, fid, "preview", decision={"kind": "quality", "settings": settings})
    assert preview["proposal"]["changed_cells"] >= 4
    assert preview["quality"]["removed_row"] == 1
    assert current(client, fid)["preview"]["rows"] == initial["preview"]["rows"]
    job(client, fid, "decision", decision={"kind": "quality", "settings": settings})
    changed = current(client, fid)
    assert changed["preview"]["total_rows"] == 2
    assert changed["preview"]["rows"][0] == ["001", "John Smith", "Cairo", "01234567890"]
    assert stored(client, fid)["editor_df"].index.tolist() == [0, 2]
    audit = stored(client, fid)["complete_changes"]
    assert {item["column"] for item in audit if item["removed_row"] and item["row_index"] == 1} == {"Customer_ID", "Name", "City", "Phone"}
    assert changed["changes"][-1]["quality"]["removed_row"] == 1
    restored = undo(client, fid)
    assert restored["preview"]["rows"] == initial["preview"]["rows"]
    assert stored(client, fid)["editor_df"].index.tolist() == [0, 1, 2]


def test_keep_records_is_audited_reversible_and_expires_when_values_change(client):
    fid, initial = upload(client, ["Customer_ID", "Name", "City", "Phone"], records())
    config = {"tool": "record_matching", "columns": ["Name", "City"], "threshold": .8, "block_by": ""}
    job(client, fid, "decision", decision={"kind": "quality", "settings": {**config, "action": "keep_both", "left_row": 0, "right_row": 1}})
    kept = current(client, fid)
    assert kept["preview"]["rows"] == initial["preview"]["rows"]
    assert kept["changes"][-1]["action"] == "keep_records"
    assert kept["changes"][-1]["changed_cells"] == 0
    analyzed = job(client, fid, "quality_review", quality=config)
    assert analyzed["kept_pairs_skipped"] == 1
    assert not any({pair["left_row"], pair["right_row"]} == {0, 1} for pair in analyzed["pairs"])
    replace(client, fid, "Phone", 0, "01098765432")
    analyzed = job(client, fid, "quality_review", quality=config)
    assert any({pair["left_row"], pair["right_row"]} == {0, 1} for pair in analyzed["pairs"])
    undo(client, fid)  # Restoring the complete records restores the reviewed judgement.
    analyzed = job(client, fid, "quality_review", quality=config)
    assert analyzed["kept_pairs_skipped"] == 1
    undo(client, fid)
    analyzed = job(client, fid, "quality_review", quality=config)
    assert any({pair["left_row"], pair["right_row"]} == {0, 1} for pair in analyzed["pairs"])
    assert not stored(client, fid).get("kept_record_pairs")


def test_merge_transfers_date_interpretation_estimates_and_manual_acceptance(client):
    fid, _ = upload(client, ["Customer_ID", "Name", "City", "Event_Date", "Reading", "Email"], [
        ["001", "Jon Smith", "Cairo", "", "", ""],
        ["002", "John Smith", "Cairo", "02/03/2024", "", ""],
        ["003", "Mary Jones", "Alexandria", "13/03/2024", 20, "mary@example.com"],
    ])
    job(client, fid, "decision", decision={"kind": "fix", "body": {"revision": 0, "column": "Event_Date", "row_index": 1, "scope": "cell", "action": "normalize_dates", "parameters": {"interpretation": "day_first", "output_format": "DD/MM/YYYY"}}})
    replace(client, fid, "Email", 1, "No Email Provided")
    revision = current(client, fid)["revision"]
    job(client, fid, "decision", decision={"kind": "fix", "body": {"revision": revision, "column": "Reading", "row_index": 1, "scope": "cell", "action": "impute_missing_values", "parameters": {"method": "mean"}}})
    before_merge = current(client, fid)
    assert ("Reading", 1) in estimated_cells(stored(client, fid))
    assert known_date_formats(stored(client, fid))[("Event_Date", 1)] == "DD/MM/YYYY"
    quality(client, fid, "record_matching", action="merge", columns=["Name", "City"], threshold=.8, block_by="", left_row=0, right_row=1, keep_row=0, choices={"Customer_ID": "left", "Name": "right"}, confirmed=True)
    merged = current(client, fid)
    rec = stored(client, fid)
    assert ("Reading", 0) in estimated_cells(rec)
    assert ("Reading", 1) not in estimated_cells(rec)
    assert known_date_formats(rec)[("Event_Date", 0)] == "DD/MM/YYYY"
    assert ("Event_Date", 1) not in known_date_formats(rec)
    assert any(item["column"] == "Email" and item["row_index"] == 0 and item["value"] == "No Email Provided" for item in manual_acceptances(rec))
    assert merged["preview"]["is_imputed"][0][4]
    assert not flags(merged, "Email", 0, "email")
    preview = client.post(f"/api/files/{fid}/editor/fix", json={"revision": merged["revision"], "column": "Event_Date", "row_index": 0, "scope": "cell", "action": "normalize_dates", "parameters": {"interpretation": "preserve", "output_format": "YYYY-MM-DD"}})
    assert preview.status_code == 200, preview.text
    assert preview.json()["proposal"]["examples"][0]["after"] == "2024-03-02"
    restored = undo(client, fid)
    assert restored["preview"]["rows"] == before_merge["preview"]["rows"]
    assert ("Reading", 1) in estimated_cells(stored(client, fid))
    assert known_date_formats(stored(client, fid))[("Event_Date", 1)] == "DD/MM/YYYY"

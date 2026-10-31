import copy

import pandas as pd
import pytest

from app.core.cross_column import apply, findings, review, validate_settings


def record(data, **extra):
    return {"editor_df": pd.DataFrame(data, dtype=object), "missing_marker_review_version": 1, **extra}


def equation(**extra):
    return {"id": "total", "label": "Check total", "kind": "arithmetic", "target": "Total", "left": "Quantity", "right": "Price", "arithmetic": "multiply", **extra}


def save(rec, rules):
    return apply(rec, {"action": "save_rules", "rules": rules})


def test_rules_only_flag_and_return_exact_location_without_mutation():
    rec = record({"Quantity": [2, 3], "Price": [10, 20], "Total": [20, 50]})
    original = rec["editor_df"].copy(deep=True)
    result = review(rec, {"rules": [equation()]})
    assert result["finding_count"] == result["affected_cells"] == 1
    assert result["findings"][0]["row_index"] == 1
    assert result["findings"][0]["spreadsheet_row"] == 3
    assert result["findings"][0]["column"] == "Total"
    assert result["findings"][0]["before"] == 50
    assert result["findings"][0]["expected"] == "60"
    assert "cross_column_rules" not in rec
    pd.testing.assert_frame_equal(original, rec["editor_df"])
    save(rec, [equation()])
    assert len(findings(rec)) == 1
    pd.testing.assert_frame_equal(original, rec["editor_df"])


def test_recalculate_only_reviewed_rule_rows_with_valid_donors():
    rec = record({"Quantity": [2, 3, None, "unknown", 2], "Price": [10, 20, 7, 8, 9], "Total": [0, 1, 5, 6, 18]})
    save(rec, [equation()])
    after, detail = apply(rec, {"action": "recalculate", "rule_id": "total", "row_indices": [1, 2, 3]})
    assert after.Total.tolist() == [0, "60", 5, 6, 18]
    assert detail["changed_cells"] == 1
    assert detail["skipped_count"] == 2
    assert rec["editor_df"].Total.tolist() == [0, 1, 5, 6, 18]


@pytest.mark.parametrize("operation,expected", [("add", "5"), ("subtract", "1"), ("multiply", "6"), ("divide", "1.5")])
def test_explicit_arithmetic_operations(operation, expected):
    rec = record({"Quantity": [3], "Price": [2], "Total": [None]})
    save(rec, [equation(arithmetic=operation)])
    after, _ = apply(rec, {"action": "recalculate", "rule_id": "total"})
    assert after.at[0, "Total"] == expected


def test_tolerance_and_decimal_precision():
    rec = record({"Quantity": ["0.1", "123456789012345678901234567890.1"], "Price": ["0.2", "1"], "Total": ["0.0200001", "0"]})
    save(rec, [equation(tolerance=0.000001)])
    assert [item["row_index"] for item in findings(rec)] == [1]
    after, _ = apply(rec, {"action": "recalculate", "rule_id": "total"})
    assert after.at[0, "Total"] == "0.0200001"
    assert after.at[1, "Total"] == "123456789012345678901234567890.1"


def test_zero_division_and_nonfinite_donors_not_repaired():
    rec = record({"Quantity": [4, "inf", "nan", "4"], "Price": [0, 2, 2, "2"], "Total": [6, 7, 8, 0]})
    save(rec, [equation(arithmetic="divide")])
    flags = findings(rec)
    assert flags[0]["status"] == "uncheckable"
    assert "division" in flags[0]["message"]
    after, detail = apply(rec, {"action": "recalculate", "rule_id": "total"})
    assert after.Total.tolist() == [6, 7, 8, "2"]
    assert detail["skipped_count"] == 3


def test_unknown_marker_text_is_not_automatically_missing():
    rec = record({"State": ["yes", "yes", "no", "yes"], "Email": [None, "NA", None, "a@b.com"]})
    rule = {"id": "required", "label": "Contact needs email", "kind": "required_if", "target": "Email", "condition_column": "State", "condition_value": "yes"}
    save(rec, [rule])
    assert [flag["row_index"] for flag in findings(rec)] == [0]
    rec["missing_marker_policies"] = {"Email": {"convert": True}}
    assert [flag["row_index"] for flag in findings(rec)] == [0, 1]


def test_condition_matching_is_exact_and_can_use_not_equal():
    rec = record({"State": ["yes", "YES", "no", None], "Email": [None] * 4})
    rule = {"id": "r", "kind": "required_if", "target": "Email", "condition_column": "State", "condition_value": "yes", "operator": "ne"}
    save(rec, [rule])
    assert [flag["row_index"] for flag in findings(rec)] == [1, 2, 3]


def test_ambiguous_dates_need_explicit_interpretation_and_compare_time():
    rec = record({"Start": ["01/02/2024", "2024-01-01T10:00:00"], "End": ["02/01/2024", "2024-01-01T09:00:00"]})
    rule = {"id": "date", "kind": "compare", "target": "End", "left": "Start", "value_type": "date", "operator": "ge"}
    save(rec, [rule])
    assert findings(rec)[0]["status"] == "uncheckable"
    assert "Ambiguous" in findings(rec)[0]["message"]
    rule["interpretation"] = "month_first"
    save(rec, [rule])
    assert [flag["row_index"] for flag in findings(rec)] == [1]
    rule["interpretation"] = "day_first"
    save(rec, [rule])
    assert len(findings(rec)) == 2


def test_per_row_confirmed_date_format_takes_precedence_over_guessing():
    rec = record({"Start": ["01/02/2024"], "End": ["02/01/2024"]}, editor_changes=[{"id": "a", "action": "normalize_dates", "column": "Start", "parameters": {"output_format": "MM/DD/YYYY"}, "date_format_rows": [0]}, {"id": "b", "action": "normalize_dates", "column": "End", "parameters": {"output_format": "MM/DD/YYYY"}, "date_format_rows": [0]}])
    rule = {"id": "date", "kind": "compare", "target": "End", "left": "Start", "value_type": "date", "operator": "ge"}
    save(rec, [rule])
    assert findings(rec) == []


def test_timezone_aware_and_naive_dates_are_not_compared():
    rec = record({"Start": ["2024-01-01T10:00:00+00:00"], "End": ["2024-01-01T11:00:00"]})
    save(rec, [{"id": "date", "kind": "compare", "target": "End", "left": "Start", "value_type": "date", "operator": "ge"}])
    assert "timezone-aware" in findings(rec)[0]["message"]


@pytest.mark.parametrize("value", ["$20", "10%", "20 kg", "__import__('os').system('x')"])
def test_arithmetic_never_guesses_units_or_evaluates_expression(value):
    rec = record({"Quantity": [value], "Price": [2], "Total": [0]})
    save(rec, [equation()])
    assert findings(rec)[0]["repairable"] is False
    with pytest.raises(ValueError, match="No affected cells"):
        apply(rec, {"action": "recalculate", "rule_id": "total"})


def test_unknown_columns_and_identifiers_protected_before_commit():
    rec = record({"Quantity": [2], "Price": [5], "Total": ["0009"]})
    with pytest.raises(ValueError, match="protected identifier"):
        save(rec, [equation()])
    assert "cross_column_rules" not in rec
    with pytest.raises(ValueError, match="unknown column"):
        save(rec, [equation(target="Missing")])


def test_declared_identifier_cannot_be_overridden_by_numeric_rule():
    rec = record({"Quantity": [2], "Price": [5], "Total": [9]}, column_rules={"Total": {"type": "identifier"}})
    with pytest.raises(ValueError, match="protected identifier"):
        save(rec, [equation()])


def test_clear_is_explicit_limited_to_flagged_nonempty_targets():
    rec = record({"Quantity": [2, 3, 4], "Price": [5, 5, 5], "Total": [9, 15, None]})
    save(rec, [equation()])
    after, detail = apply(rec, {"action": "clear", "rule_id": "total"})
    assert after.Total.tolist() == [None, 15, None]
    assert detail["changed_cells"] == 1


def test_recalculate_blocks_new_conflict_with_other_saved_rule_atomically():
    rec = record({"Quantity": [3], "Price": [5], "Total": [5], "Limit": [10]})
    maximum = {"id": "max", "kind": "compare", "target": "Total", "left": "Limit", "operator": "le"}
    save(rec, [equation(), maximum])
    with pytest.raises(ValueError, match="conflicts"):
        apply(rec, {"action": "recalculate", "rule_id": "total"})
    assert rec["editor_df"].at[0, "Total"] == 5


def test_preview_limits_details_but_bulk_correction_and_persistent_flags_cover_all_rows():
    rec = record({"Quantity": [2]*650, "Price": [5]*650, "Total": [0]*650})
    save(rec, [equation()])
    detail = review(rec, {"rules": rec["cross_column_rules"]})
    assert detail["finding_count"] == detail["affected_cells"] == 650
    assert len(detail["findings"]) == 500
    assert detail["findings_truncated"]
    assert len(findings(rec)) == 650
    after, corrected = apply(rec, {"action": "recalculate", "rule_id": "total"})
    assert corrected["changed_cells"] == 650
    assert after.Total.tolist() == ["10"]*650
    assert len(corrected["findings"]) == 500


def test_cancellation_does_not_save_rules_or_modify_values():
    rec = record({"Quantity": [2], "Price": [5], "Total": [9]})
    def cancel():
        raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        apply(rec, {"rules": [equation()]}, cancel)
    assert "cross_column_rules" not in rec
    assert rec["editor_df"].at[0, "Total"] == 9


@pytest.mark.parametrize("settings", [{"rules": [equation()] * 31}, {"rules": [equation(), equation()]}, {"rules": [equation(tolerance=-1)]}, {"rules": [equation(tolerance=float("inf"))]}, {"rules": [equation(arithmetic="eval")]}, {"rules": [equation(expression="a * b")]}, {"action": "recalculate", "rule_id": "total", "row_indices": [-1]}, {"action": "recalculate", "rule_id": "total", "row_indices": [True]}, {"action": "recalculate", "rule_id": "total", "row_indices": []}])
def test_malformed_rules_rejected(settings):
    with pytest.raises(ValueError):
        validate_settings(settings)

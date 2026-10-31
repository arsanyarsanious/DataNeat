import copy

import pandas as pd
import pytest

from app.core import record_matching as matching


def record(values=None):
    return {"editor_df": pd.DataFrame(values or {
        "Name": ["John Smith", "Jon Smith", "Mary Jones"],
        "City": ["Cairo", "Cairo", "Giza"],
        "Email": ["john@example.com", None, "mary@example.com"],
    }, dtype=object)}


def config(**kwargs):
    return {"columns": ["Name", "City"], **kwargs}


def test_review_variants_is_only_a_suggestion_and_preserves_source():
    rec = record()
    original = rec["editor_df"].copy(deep=True)
    result = matching.review(rec, config())
    assert result["pairs"][0]["left_row"] == 0
    assert result["pairs"][0]["right_row"] == 1
    assert 0.9 < result["pairs"][0]["score"] < 1
    assert result["pairs"][0]["left_values"]["Email"] == "john@example.com"
    assert result["pairs"][0]["conflicts"] == ["Name"]
    assert result["exhaustive"] is False
    assert "not probabilities" in " ".join(result["warnings"])
    pd.testing.assert_frame_equal(rec["editor_df"], original)


def test_blank_fields_never_inflate_agreement_and_single_shared_field_is_insufficient():
    rec = record({"Name": ["John Smith", "John Smith"], "City": [None, ""], "Third": [None, None]})
    assert matching.review(rec, config(columns=["Name", "City", "Third"], threshold=0))['pairs'] == []
    rec = record({"Name": ["John Smith", "John Smith"], "City": ["Cairo", "Cairo"], "Third": [None, "Giza"]})
    result = matching.review(rec, config(columns=["Name", "City", "Third"], threshold=0.6))
    assert result["pairs"][0]["score"] == pytest.approx(2 / 3, abs=0.0001)
    assert matching.review(rec, config(columns=["Name", "City", "Third"], threshold=0.85))["pairs"] == []


@pytest.mark.parametrize("column,values", [
    ("Email", ["john@example.com", "jon@example.com"]),
    ("CustomerID", ["000123", "000124"]),
    ("Value", ["12345", "12346"]),
    ("Salary", ["$12345", "$12346"]),
])
def test_identifiers_email_and_numeric_fields_are_not_fuzzy_text(column, values):
    rec = record({"Name": ["John Smith", "John Smith"], column: values})
    assert matching.review(rec, config(columns=["Name", column], threshold=0.5))["pairs"] == []


def test_exact_blocking_excludes_different_values_and_reports_empty_blocks():
    rec = record({"Name": ["John Smith"] * 4, "City": ["Cairo"] * 4, "Group": ["A", "B", None, "A"]})
    result = matching.review(rec, config(block_by="Group"))
    assert [(item["left_row"], item["right_row"]) for item in result["pairs"]] == [(0, 3)]
    assert result["coverage"]["rows_without_block_value"] == 1
    assert result["coverage"]["searched_rows"] == 3
    assert "excluded" in " ".join(result["warnings"])


def test_candidate_budget_is_bounded_deterministic_and_truthfully_reported(monkeypatch):
    monkeypatch.setattr(matching, "MAX_COMPARISONS", 7)
    rec = record({"Name": [f"Person {i}" for i in range(100)], "City": ["Cairo"] * 100})
    one = matching.review(rec, config(threshold=0.7))
    two = matching.review(rec, config(threshold=0.7))
    assert one["compared_pairs"] <= 7
    assert one["coverage"]["candidate_positions"] > 7
    assert one["coverage"]["sampled_candidates"] is True
    assert one["truncated"] is True
    assert one["pairs"] == two["pairs"]
    assert "comparison budget" in " ".join(one["warnings"])


def test_returned_pair_payload_is_capped(monkeypatch):
    monkeypatch.setattr(matching, "MAX_RESULTS", 2)
    rec = record({"Name": ["John Smith"] * 10, "City": ["Cairo"] * 10})
    result = matching.review(rec, config())
    assert len(result["pairs"]) == 2
    assert result["matched_pairs"] > 2
    assert result["truncated"] is True
    assert "highest-scoring pairs" in " ".join(result["warnings"])


def test_merge_requires_all_conflicts_and_confirmation_before_changing_anything():
    rec = record()
    original = rec["editor_df"].copy(deep=True)
    options = config(action="merge", left_row=0, right_row=1, keep_row=1, choices={})
    with pytest.raises(ValueError, match="confirm"):
        matching.apply(rec, options)
    with pytest.raises(ValueError, match="Name"):
        matching.apply(rec, {**options, "confirmed": True})
    pd.testing.assert_frame_equal(rec["editor_df"], original)


def test_merge_retains_chosen_original_index_and_preserves_unambiguous_values():
    rec = record()
    rec["editor_df"].index = [5, 19, 27]
    result, metadata = matching.apply(rec, config(action="merge", left_row=5, right_row=19, keep_row=19, choices={"Name": "left", "Email": "right"}, confirmed=True))
    assert list(result.index) == [19, 27]
    assert result.at[19, "Name"] == "John Smith"
    # A non-conflicting donor value cannot be discarded by selecting its blank peer.
    assert result.at[19, "Email"] == "john@example.com"
    assert metadata["retained_row"] == 19
    assert metadata["removed_row"] == 5
    assert metadata["changed_cells"] == 2
    assert metadata["source_rows"] == {"Name": 5, "City": 19, "Email": 5}
    assert list(rec["editor_df"].index) == [5, 19, 27]


def test_source_rows_tracks_right_choice_coalesced_values_and_unchanged_survivor():
    rec = record({"Name": ["John", "Jon"], "City": [None, "Cairo"], "Date": ["01/02/2024", "01/02/2024"], "Other": [None, None]})
    rec["editor_df"].index = [12, 20]
    result, metadata = matching.apply(rec, config(action="merge", left_row=12, right_row=20, keep_row=12, choices={"Name": "right"}, confirmed=True))
    assert metadata["source_rows"] == {"Name": 20, "City": 20, "Date": 12, "Other": 12}
    assert result.at[12, "Name"] == "Jon"
    assert result.at[12, "City"] == "Cairo"


def test_keep_both_is_content_scoped_and_reappears_after_a_later_edit():
    rec = record()
    original = rec["editor_df"].copy(deep=True)
    result, metadata = matching.apply(rec, config(action="keep_both", left_row=0, right_row=1))
    assert metadata["changed_cells"] == 0
    pd.testing.assert_frame_equal(result, original)
    assert matching.review(rec, config())["pairs"] == []
    assert matching.review(rec, config())["kept_pairs_skipped"] == 1
    rec["editor_df"].at[0, "Email"] = "changed@example.com"
    assert matching.review(rec, config())["pairs"]


def test_reversed_keep_both_pair_replaces_previous_decision_without_duplicate():
    rec = record()
    matching.apply(rec, config(action="keep_both", left_row=0, right_row=1))
    matching.apply(rec, config(action="keep_both", left_row=1, right_row=0))
    assert len(rec["kept_record_pairs"]) == 1
    assert matching.review(rec, config())["pairs"] == []


def test_stale_rows_unknown_fields_and_mismatched_block_fail_before_merge():
    rec = record()
    base = config(action="merge", left_row=0, right_row=1, keep_row=0, choices={"Name": "left"}, confirmed=True)
    with pytest.raises(ValueError, match="no longer exists"):
        matching.apply(rec, {**base, "right_row": 99})
    with pytest.raises(ValueError, match="Unknown merge fields"):
        matching.apply(rec, {**base, "choices": {"Name": "left", "Missing": "right"}})
    with pytest.raises(ValueError, match="blocking value"):
        matching.apply(rec, {**base, "block_by": "Email"})


def test_unreviewed_marker_labels_are_literal_values_not_silently_empty():
    rec = record({"Name": ["John Smith", "John Smith"], "City": ["NA", "NA"]})
    assert matching.review(rec, config())["pairs"][0]["score"] == 1


def test_cancellation_does_not_partially_mutate_source():
    rec = record()
    original = copy.deepcopy(rec)
    def cancelled():
        raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        matching.apply(rec, config(action="merge", left_row=0, right_row=1, keep_row=1, choices={"Name": "left"}, confirmed=True), cancelled)
    pd.testing.assert_frame_equal(rec["editor_df"], original["editor_df"])


@pytest.mark.parametrize("settings", [
    {"columns": ["Name"]},
    {"columns": ["Name", "Name"]},
    {"columns": ["Name", "City"], "threshold": float("nan")},
    {"columns": ["Name", "City"], "threshold": True},
    {"columns": ["Name", "City"], "action": "auto_merge"},
])
def test_invalid_settings_are_rejected(settings):
    with pytest.raises(ValueError):
        matching.validate_settings(settings)

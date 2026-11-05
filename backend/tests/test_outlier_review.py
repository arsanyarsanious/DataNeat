import copy

import pandas as pd
import pytest

from app.core.outlier_review import apply, review


def record(values, groups=None):
    df = pd.DataFrame({"Value": values}, dtype=object)
    if groups:
        df["Group"] = groups
    return {"editor_df": df, "editor_profile": {"columns": [{"column_name": "Value", "detected_type": "integer"}]}}


def test_iqr_check_and_explicit_actions_do_not_touch_observed_neighbors():
    data = record([10, 11, 12, 13, 14, 100, None])
    cfg = {"column": "Value"}
    result = review(data, cfg)
    assert result["all_row_indices"] == [5]
    assert data["editor_df"].at[5, "Value"] == 100
    with pytest.raises(ValueError, match="Confirm"):
        apply(data, {**cfg, "action": "clear"})
    cleared, _ = apply(copy.deepcopy(data), {**cfg, "action": "clear", "confirmed": True})
    assert cleared["Value"].tolist() == [10, 11, 12, 13, 14, None, None]
    capped, detail = apply(copy.deepcopy(data), {**cfg, "action": "cap", "confirmed": True})
    assert capped.at[5, "Value"] == result["findings"][0]["upper"]
    assert detail["affected_rows"] == 1
    apply(data, {**cfg, "action": "keep"})
    assert review(data, cfg)["count"] == 0
    data["editor_df"].at[5, "Value"] = 101
    assert review(data, cfg)["count"] == 1


def test_group_and_zero_mad_are_explained():
    data = record([1, 1, 1, 1, 100, 1000, 1001, 1002, 1003, 1004], ["A"] * 5 + ["B"] * 5)
    result = review(data, {"column": "Value", "group_by": ["Group"]})
    assert result["all_row_indices"] == [4]
    mad = review(data, {"column": "Value", "method": "mad", "multiplier": 3, "group_by": ["Group"]})
    assert any("MAD is zero" in warning for warning in mad["warnings"])


def test_literals_identifiers_and_stale_row_selections_block():
    data = record([1, 2, 3, 4, "NA", 100])
    with pytest.raises(ValueError, match='spreadsheet row 6'):
        review(data, {"column": "Value"})
    data = record([1, 2, 3, 4, 5, 100])
    data["column_rules"] = {"Value": {"type": "identifier"}}
    with pytest.raises(ValueError, match="protected"):
        review(data, {"column": "Value"})
    data.pop("column_rules")
    with pytest.raises(ValueError, match="no longer"):
        apply(data, {"column": "Value", "action": "clear", "confirmed": True, "row_indices": [0]})


def test_custom_replacement_is_reviewed_and_targets_only_selected_outliers():
    data = record([10, 11, 12, 13, 14, 100, 200, None])
    config = {"column": "Value", "action": "replace", "value": "15",
              "row_indices": [5], "confirmed": True, "multiplier": 0.5}
    after, detail = apply(data, config)
    assert after.at[5, "Value"] == 15
    assert after.at[6, "Value"] == 200
    assert after.at[7, "Value"] is None
    assert detail["affected_rows"] == 1
    with pytest.raises(ValueError):
        apply(data, {**config, "value": "bad"})


def test_cap_resolves_exact_reviewed_value_and_changed_value_is_rechecked():
    data = record([10, 11, 12, 13, 14, 100, None])
    settings = {"column": "Value", "action": "cap", "confirmed": True}
    expected = review(data, settings)["findings"][0]["after"]
    after, _ = apply(data, settings)
    assert after.at[5, "Value"] == expected
    data["editor_df"] = after
    assert review(data, settings)["count"] == 0
    # Subsequent changes to other values can tighten bounds around the reviewed cap.
    data["editor_df"].loc[0:4, "Value"] = [1, 2, 3, 4, 5]
    assert review(data, settings)["count"] == 0
    data["editor_df"].at[5, "Value"] = 999
    assert review(data, settings)["all_row_indices"] == [5]


def test_distribution_counts_all_values_and_marks_only_current_findings():
    data = record([10, 11, 12, 13, 14, 100, None])
    result = review(data, {"column": "Value"})
    chart = result["distributions"][0]
    assert chart["median"] == 12.5
    assert chart["count"] == 6
    assert sum(bin["count"] for bin in chart["bins"]) == 6
    assert sum(bin["flagged"] for bin in chart["bins"]) == result["count"] == 1
    assert chart["points"] == [{"row": 7, "value": 100}]
    apply(data, {"column": "Value", "action": "keep"})
    chart = review(data, {"column": "Value"})["distributions"][0]
    assert chart["flagged_count"] == 0
    assert sum(bin["count"] for bin in chart["bins"]) == 6


def test_distribution_keeps_group_statistics_separate():
    data = record([1, 2, 3, 4, 100, 1000, 1001, 1002, 1003, 1004], ["A"] * 5 + ["B"] * 5)
    charts = review(data, {"column": "Value", "group_by": ["Group"]})["distributions"]
    assert [chart["median"] for chart in charts] == [3, 1002]
    assert [chart["count"] for chart in charts] == [5, 5]

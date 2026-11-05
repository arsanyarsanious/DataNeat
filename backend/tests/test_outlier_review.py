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

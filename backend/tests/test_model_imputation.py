import copy

import numpy as np
import pandas as pd
import pytest

from app.core import model_imputation as model


def record(length=40):
    x = np.linspace(10, 100, length)
    return {"editor_df": pd.DataFrame({"Measurement": 2 * x + 7,
                                      "Input": x, "Other": 3 * x - 11}, dtype=object)}


def settings(method="knn", **kw):
    return {"target": "Measurement", "helpers": ["Input"], "method": method,
            "neighbors": 3, **kw}


@pytest.mark.parametrize("method", ["knn", "iterative"])
def test_real_models_preserve_observations_and_review_is_read_only(method):
    item = record()
    expected = item["editor_df"].loc[20, "Measurement"]
    item["editor_df"].loc[20, "Measurement"] = None
    before = item["editor_df"].copy(deep=True)
    preview = model.review(item, settings(method))
    pd.testing.assert_frame_equal(item["editor_df"], before)
    result, detail = model.apply(item, settings(method, acknowledge=True))
    pd.testing.assert_frame_equal(item["editor_df"], before)
    pd.testing.assert_series_equal(result.loc[result.index != 20, "Measurement"], before.loc[before.index != 20, "Measurement"])
    pd.testing.assert_series_equal(result["Input"], before["Input"])
    assert abs(result.loc[20, "Measurement"] - expected) < (2 if method == "knn" else 0.01)
    assert detail["filled_count"] == detail["imputed_count"] == 1
    assert detail["imputed_rows"] == [20]
    assert detail["missing_before"] == 1 and detail["missing_after"] == 0
    assert preview["examples"] == detail["examples"]
    assert detail["validation"]["status"] == "available"
    assert detail["validation"]["held_out_count"] >= 2
    assert detail["validation"]["mae"] < detail["validation"]["baseline_mae"]


def test_knn_robust_scaling_avoids_large_unit_dominance():
    item = record(60)
    item["editor_df"]["Other"] = np.sin(np.arange(60)) * 1e9
    item["editor_df"].loc[25, "Measurement"] = ""
    first = model.review(item, settings(helpers=["Input", "Other"]))
    item["editor_df"]["Other"] /= 1e9
    second = model.review(item, settings(helpers=["Input", "Other"]))
    assert first["examples"][0]["after"] == pytest.approx(second["examples"][0]["after"])


def test_no_usable_helper_keeps_target_empty_without_mean_fallback():
    item = record()
    item["editor_df"].loc[20, ["Measurement", "Input"]] = None
    detail = model.review(item, settings())
    assert detail["missing_count"] == 1 and detail["filled_count"] == 0
    assert detail["skipped_count"] == 1 and detail["examples"] == []
    assert any("remain empty" in warning for warning in detail["warnings"])


def test_prior_estimates_excluded_from_target_and_helper_evidence():
    item = record()
    item["editor_df"].loc[20, "Measurement"] = None
    item["editor_df"].loc[19, "Measurement"] = 1e8
    item["editor_df"].loc[20, "Input"] = 1e8
    item.update(editor_changes=[{"id": "old", "action": "impute_missing_values"}],
                complete_changes=[{"step_id": "old", "column": "Measurement", "row_index": 19, "after": 1e8},
                                  {"step_id": "old", "column": "Input", "row_index": 20, "after": 1e8}])
    detail = model.review(item, settings())
    assert detail["excluded_estimates"] == 2
    assert detail["excluded_estimates_by_column"] == {"Measurement": 1, "Input": 1}
    assert detail["donor_count"] == 38
    assert detail["filled_count"] == 0


def test_held_out_target_values_are_excluded_before_scaler_fit(monkeypatch):
    item = record(40)
    item["editor_df"].loc[20, "Measurement"] = None
    original = model.RobustScaler
    training_targets = []

    class InspectScaler(original):
        def fit_transform(self, matrix, *args, **kwargs):
            training_targets.append(matrix[:, 0].copy())
            return super().fit_transform(matrix, *args, **kwargs)

    monkeypatch.setattr(model, "RobustScaler", InspectScaler)
    detail = model.review(item, settings("iterative"))
    holdout_fit, final_fit = training_targets
    assert len(holdout_fit) == 39 - detail["validation"]["held_out_count"]
    assert len(final_fit) == 39
    chosen = np.random.default_rng(model.SEED).permutation(np.flatnonzero(item["editor_df"]["Measurement"].notna()))
    holdout = chosen[:detail["validation"]["held_out_attempted"]]
    hidden_values = item["editor_df"].iloc[holdout]["Measurement"].to_numpy(dtype=float)
    assert not set(hidden_values) & set(holdout_fit)


def test_validation_is_honest_for_small_samples():
    item = record(8)
    item["editor_df"].loc[6, "Measurement"] = None
    detail = model.review(item, settings())
    assert detail["validation"]["status"] == "unavailable"
    assert detail["validation"]["mae"] is None
    assert detail["validation"]["baseline_mae"] is None
    assert detail["filled_count"] == 1


@pytest.mark.parametrize("name,values", [
    ("Customer_ID", [str(i) for i in range(10, 50)]),
    ("Input", [f"00{i}" for i in range(10, 50)]),
    ("Input", ["$10"] * 40),
    ("Input", ["10%"] * 40),
    ("Input", ["2024-01-01"] * 40),
    ("Input", ["true"] * 40),
    ("Input", ["12:30 PM"] * 40),
    ("Input", ["5 kg"] * 40),
    ("Input", ["word"] * 40),
])
def test_non_measurement_helpers_are_rejected(name, values):
    item = record()
    item["editor_df"][name] = values
    with pytest.raises(ValueError, match="numeric measurement"):
        model.review(item, settings(helpers=[name]))


@pytest.mark.parametrize("value", ["NA", "null", "empty", "unknown", float("inf"), "1e999"])
def test_no_silent_marker_conversion_or_nonfinite_ignoring(value):
    item = record()
    item["editor_df"].loc[8, "Measurement"] = value
    item["editor_df"].loc[20, "Measurement"] = None
    before = copy.deepcopy(item)
    with pytest.raises(ValueError, match="Column 'Measurement'.*spreadsheet row 10"):
        model.apply(item, settings(acknowledge=True))
    pd.testing.assert_frame_equal(item["editor_df"], before["editor_df"])


def test_unresolved_marker_helpers_and_declared_semantic_columns_are_blocked():
    item = record()
    item["editor_df"].loc[8, "Input"] = "N/A"
    with pytest.raises(ValueError, match="spreadsheet row 10"):
        model.review(item, settings())
    item = record()
    item["column_rules"] = {"Input": {"type": "percentage"}}
    with pytest.raises(ValueError, match="percentage"):
        model.review(item, settings())


def test_apply_requires_explicit_estimate_acknowledgement():
    with pytest.raises(ValueError, match="Confirm"):
        model.apply(record(), settings())


@pytest.mark.parametrize("overrides", [
    {"method": "regression"}, {"helpers": []}, {"helpers": ["Measurement"]},
    {"helpers": ["Input", "Input"]}, {"neighbors": True}, {"neighbors": 0},
    {"max_iter": 21}, {"max_iter": 0.2}, {"acknowledge": "yes"}, {"extra": 1},
])
def test_settings_bounds(overrides):
    with pytest.raises(ValueError):
        model.validate_settings(settings(**overrides))


def test_minimum_original_donors_and_varying_helper_required():
    item = record(6)
    item["editor_df"].loc[0:2, "Measurement"] = None
    with pytest.raises(ValueError, match="at least 5 original"):
        model.review(item, settings())
    item = record()
    item["editor_df"]["Input"] = "25"
    with pytest.raises(ValueError, match="helper must vary"):
        model.review(item, settings())


def test_training_sampling_and_missing_limit_are_reported(monkeypatch):
    monkeypatch.setattr(model, "MAX_TRAIN_ROWS", 20)
    item = record(70)
    item["editor_df"].loc[20, "Measurement"] = None
    detail = model.review(item, settings())
    assert detail["fit_donor_count"] == 20 and detail["donor_count"] == 69
    assert any("deterministic sample" in warning for warning in detail["warnings"])
    monkeypatch.setattr(model, "MAX_MISSING_ROWS", 1)
    item["editor_df"].loc[30, "Measurement"] = None
    with pytest.raises(ValueError, match="at most 1 missing"):
        model.review(item, settings())


def test_cooperative_cancellation_never_mutates_record():
    item = record()
    item["editor_df"].loc[20, "Measurement"] = None
    before = item["editor_df"].copy(deep=True)
    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls == 8:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        model.apply(item, settings(acknowledge=True), check)
    pd.testing.assert_frame_equal(item["editor_df"], before)


def test_original_spreadsheet_indices_retained():
    item = record()
    item["editor_df"].index = np.arange(100, 140)
    item["editor_df"].loc[120, "Measurement"] = None
    result, detail = model.apply(item, settings(acknowledge=True))
    assert result.index.tolist() == list(range(100, 140))
    assert detail["examples"][0]["spreadsheet_row"] == 122
    assert detail["imputed_rows"] == [120]

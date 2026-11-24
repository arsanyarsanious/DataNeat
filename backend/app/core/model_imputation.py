"""Reviewed multivariate estimates, fitted only from surviving observations.

The target is never inferred from a row number. Helpers are explicitly selected
plain measurements. Validation hides observed targets before fitting either the
scaler or imputer, and uses a separate fit from the final estimates.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from sklearn.experimental import enable_iterative_imputer  # noqa: F401: experimental API opt-in
from sklearn.impute import IterativeImputer, KNNImputer
from sklearn.exceptions import ConvergenceWarning
from sklearn.preprocessing import RobustScaler
from threadpoolctl import threadpool_limits

from .common import ACTIVE_MARKERS, missing, scalar
from .imputation import number
from .type_detector import detect_column_type

MAX_TRAIN_ROWS = 2000
MAX_MISSING_ROWS = 10000
MAX_HELPERS = 8
TRANSFORM_BATCH = 128
VALIDATION_MAX = 200
SEED = 41729


def validate_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError("Choose model imputation settings")
    unknown = set(settings) - {"method", "target", "helpers", "neighbors", "max_iter", "acknowledge", "inconsistencies_acknowledged"}
    if unknown:
        raise ValueError(f"Unsupported model imputation setting: {sorted(unknown)[0]}")
    method = settings.get("method", "knn")
    if method not in ("knn", "iterative"):
        raise ValueError("Choose KNN or Iterative imputation")
    target = settings.get("target")
    if not isinstance(target, str) or not target.strip() or len(target) > 500:
        raise ValueError("Choose a target measurement column")
    helpers = settings.get("helpers", [])
    if (not isinstance(helpers, list) or not 1 <= len(helpers) <= MAX_HELPERS
            or any(not isinstance(name, str) or not name or len(name) > 500 for name in helpers)
            or len(set(helpers)) != len(helpers) or target in helpers):
        raise ValueError(f"Choose 1–{MAX_HELPERS} distinct helper columns, different from the target")
    neighbors, max_iter = settings.get("neighbors", 5), settings.get("max_iter", 10)
    if type(neighbors) is not int or not 1 <= neighbors <= 30:
        raise ValueError("KNN neighbors must be a whole number from 1 to 30")
    if type(max_iter) is not int or not 1 <= max_iter <= 20:
        raise ValueError("Iterative rounds must be a whole number from 1 to 20")
    acknowledge = settings.get("acknowledge", False)
    if type(acknowledge) is not bool:
        raise ValueError("Confirm that model-filled values are estimates")
    return dict(method=method, target=target, helpers=helpers[:], neighbors=neighbors,
                max_iter=max_iter, acknowledge=acknowledge, inconsistencies_acknowledged=settings.get("inconsistencies_acknowledged") is True)


def _empty(value):
    # Marker labels such as NA/null remain observed text until explicitly converted.
    return missing(value, markers=[""])


def _prepare(record, settings, check):
    from .workflow import estimated_cells

    df = record["editor_df"]
    columns = [settings["target"], *settings["helpers"]]
    if any(name not in df for name in columns):
        raise ValueError("The target and all helpers must exist in the current sheet")
    if not df.index.is_unique:
        raise ValueError("Model imputation needs unique source row indices")
    estimates = estimated_cells(record)
    matrix = np.full((len(df), len(columns)), np.nan, dtype=float)
    excluded = {name: 0 for name in columns}
    rules = record.get("column_rules", {})
    token = ACTIVE_MARKERS.set(frozenset({""}))
    try:
        for column_position, name in enumerate(columns):
            check()
            rule_kind = rules.get(name, {}).get("type", "")
            if rule_kind not in ("", "numeric", "salary"):
                raise ValueError(f"Column '{name}': model imputation supports ordinary numeric measurements, not {rule_kind} columns")
            series = df[name]
            observed = series.loc[~series.map(_empty)]
            # Sampling is for semantic classification only; every value is parsed below.
            sample = observed.iloc[np.linspace(0, len(observed) - 1, min(1000, len(observed)), dtype=int)] if len(observed) else observed
            kind = "decimal" if rule_kind in ("numeric", "salary") else detect_column_type(sample.rename(name))["type"]
            if kind not in ("integer", "decimal"):
                raise ValueError(f"Column '{name}': use a plain numeric measurement; detected {kind}. Identifiers, dates, text, currency and percentages are excluded")
            for position, (index, value) in enumerate(series.items()):
                if position % 512 == 0:
                    check()
                if _empty(value):
                    continue
                if (name, index) in estimates:
                    excluded[name] += 1
                    continue
                try:
                    parsed = number(value)
                    if isinstance(value, str) and value.strip().lstrip("+").startswith("0") and value.strip().lstrip("+").isdigit() and len(value.strip().lstrip("+")) > 1:
                        raise ValueError("Zero-padded identifiers are excluded")
                    if abs(parsed) > 1e100:
                        raise ValueError("Value exceeds the model's supported numeric range")
                    matrix[position, column_position] = parsed
                except (ValueError, TypeError, OverflowError) as exc:
                    raise ValueError(f"Column '{name}', spreadsheet row {int(index) + 2}, value {str(value)!r}: {exc}") from exc
    finally:
        ACTIVE_MARKERS.reset(token)
    target_missing = np.asarray([_empty(value) for value in df[settings["target"]]], dtype=bool)
    if int(target_missing.sum()) > MAX_MISSING_ROWS:
        raise ValueError(f"Model imputation supports at most {MAX_MISSING_ROWS:,} missing target cells per run; this column has {int(target_missing.sum()):,}")
    donor_positions = np.flatnonzero(np.isfinite(matrix[:, 0]))
    required = max(5, settings["neighbors"] if settings["method"] == "knn" else 5)
    if len(donor_positions) < required:
        raise ValueError(f"Column '{settings['target']}': at least {required} original observed numeric values are required; prior estimates cannot be donors")
    train_positions = _sample(donor_positions, MAX_TRAIN_ROWS)
    helpers = matrix[train_positions, 1:]
    for position, name in enumerate(settings["helpers"]):
        valid = helpers[:, position][np.isfinite(helpers[:, position])]
        if not len(valid):
            raise ValueError(f"Helper column '{name}' has no original observations among the training donors")
    if not any(len(np.unique(helpers[:, position][np.isfinite(helpers[:, position])])) > 1 for position in range(helpers.shape[1])):
        raise ValueError("At least one helper must vary among the observed target rows")
    return df, matrix, target_missing, donor_positions, train_positions, excluded


def _sample(positions, maximum):
    if len(positions) <= maximum:
        return positions.copy()
    return np.sort(np.random.default_rng(SEED).choice(positions, size=maximum, replace=False))


def _new_imputer(settings, donor_count):
    if settings["method"] == "knn":
        return KNNImputer(n_neighbors=min(settings["neighbors"], donor_count), weights="distance", keep_empty_features=True)
    return IterativeImputer(max_iter=settings["max_iter"], initial_strategy="median",
                            random_state=SEED, sample_posterior=False,
                            skip_complete=False, keep_empty_features=True)


def _fit_predict(matrix, train_positions, query_positions, settings, check):
    """No query row participates in fitting, scaling or helper initialization."""
    check()
    training = matrix[train_positions].copy()
    # No prediction can use a helper that has no observed training values.
    available = np.isfinite(training[:, 1:]).any(axis=0)
    if not available.any():
        return {}, ["No original helper observations are available for this fit"]
    selected = np.r_[True, available]
    training = training[:, selected]
    scaler = RobustScaler()
    imputer = _new_imputer(settings, len(training))
    notices = []
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=1):
        warnings.simplefilter("always", ConvergenceWarning)
        scaled = scaler.fit_transform(training)
        if not np.isfinite(scaled[~np.isnan(scaled)]).all():
            raise ValueError("Numeric ranges are too large for stable model fitting; rescale the measurements first")
        imputer.fit(scaled)
        check()
        predictions = {}
        donor_helpers = np.isfinite(training[:, 1:])
        for start in range(0, len(query_positions), TRANSFORM_BATCH):
            check()
            positions = query_positions[start:start + TRANSFORM_BATCH]
            query = matrix[positions][:, selected].copy()
            query[:, 0] = np.nan
            # KNN's no-distance fallback is deliberately not offered as a model estimate.
            usable = np.asarray([bool(np.any(donor_helpers & np.isfinite(row[1:]), axis=1).any()) for row in query])
            if not usable.any():
                continue
            transformed = imputer.transform(scaler.transform(query[usable]))
            values = scaler.inverse_transform(transformed)[:, 0]
            if not np.isfinite(values).all():
                raise ValueError("The model produced a nonfinite estimate; no changes were applied")
            predictions.update((int(position), float(value)) for position, value in zip(positions[usable], values))
        if any(isinstance(item.message, ConvergenceWarning) for item in caught):
            notices.append("Iterative fitting reached the selected round limit before convergence; review the estimates and validation")
    check()
    return predictions, notices


def _validate(matrix, donor_positions, settings, check):
    required = max(5, settings["neighbors"] if settings["method"] == "knn" else 5)
    held_out_count = min(VALIDATION_MAX, max(2, int(len(donor_positions) * 0.2)), len(donor_positions) - required)
    base = {"method": "deterministic held-out target values", "status": "unavailable",
            "held_out_count": 0, "mae": None, "baseline_mae": None,
            "baseline": "training-target median", "seed": SEED,
            "explanation": "This checks hidden observed values, not the true unknown missing values. Random holdout does not validate future or time-series prediction."}
    if len(donor_positions) < 10 or held_out_count < 2:
        return {**base, "reason": "At least 10 original target observations are needed for a meaningful held-out check"}, []
    chosen = np.random.default_rng(SEED).permutation(donor_positions)
    test_positions, remaining = chosen[:held_out_count], chosen[held_out_count:]
    train_positions = _sample(remaining, MAX_TRAIN_ROWS)
    # Remove held-out targets even from the working matrix, preventing leakage
    # if this function is changed later to include additional fitting passes.
    masked = matrix.copy()
    masked[test_positions, 0] = np.nan
    predictions, notices = _fit_predict(masked, train_positions, test_positions, settings, check)
    if len(predictions) < 2:
        return {**base, "reason": "Too few held-out rows have usable original helper measurements", "held_out_attempted": int(held_out_count)}, notices
    rows = np.asarray(sorted(predictions), dtype=int)
    truth = matrix[rows, 0]
    predicted = np.asarray([predictions[int(row)] for row in rows])
    median = float(np.median(matrix[train_positions, 0]))
    errors, baseline_errors = np.abs(truth - predicted), np.abs(truth - median)
    if not np.isfinite(errors).all() or not np.isfinite(baseline_errors).all():
        return {**base, "reason": "Numeric ranges prevented a finite validation error calculation"}, notices
    mae = math.fsum(float(value) / len(errors) for value in errors)
    baseline = math.fsum(float(value) / len(baseline_errors) for value in baseline_errors)
    return {**base, "status": "available", "held_out_count": len(rows),
            "held_out_attempted": int(held_out_count), "training_count": len(train_positions),
            "mae": mae, "baseline_mae": baseline, "better_than_baseline": mae < baseline}, notices


def _run(record, settings, check):
    settings = validate_settings(settings)
    check = check or (lambda: None)
    check()
    df, matrix, missing_mask, donors, train, excluded = _prepare(record, settings, check)
    queries = np.flatnonzero(missing_mask)
    validation, notices = _validate(matrix, donors, settings, check)
    predictions, model_notices = _fit_predict(matrix, train, queries, settings, check)
    notices += model_notices
    notices.insert(0, "Model-filled cells are estimates, not verified observations. Select helpers with a meaningful relationship to the target; avoid information derived from the target or unavailable at prediction time.")
    if validation["status"] == "available" and not validation["better_than_baseline"]:
        notices.append("The model did not outperform the simpler median baseline in this held-out check. Consider median imputation or different helpers.")
    elif validation["status"] == "unavailable":
        notices.append(f"Validation unavailable: {validation['reason']}")
    if len(train) < len(donors):
        notices.append(f"Fitting uses a deterministic sample of {len(train):,} original donors from {len(donors):,} to keep processing bounded")
    skipped = len(queries) - len(predictions)
    if skipped:
        notices.append(f"{skipped:,} missing target cells have no usable original helper values and remain empty")
    if sum(excluded.values()):
        notices.append(f"{sum(excluded.values()):,} previously estimated target/helper cells were excluded from model evidence")
    rows = [int(df.index[position]) for position in sorted(predictions)]
    examples = [{"row_index": int(df.index[position]), "spreadsheet_row": int(df.index[position]) + 2,
                 "before": scalar(df.iloc[position][settings['target']]), "after": value}
                for position, value in sorted(predictions.items())[:10]]
    metadata = {"target": settings["target"], "method": settings["method"], "helpers": settings["helpers"],
                "settings": settings, "missing_count": int(missing_mask.sum()),
                "filled_count": len(rows), "skipped_count": skipped,
                "donor_count": len(donors), "fit_donor_count": len(train),
                "excluded_estimates": sum(excluded.values()), "excluded_estimates_by_column": excluded,
                "examples": examples, "validation": validation,
                "warnings": list(dict.fromkeys(notices)),
                "computational_limits": {"training_rows": MAX_TRAIN_ROWS, "missing_target_rows": MAX_MISSING_ROWS,
                                         "helpers": MAX_HELPERS, "transform_batch_rows": TRANSFORM_BATCH},
                "imputed_rows": rows, "imputed_count": len(rows),
                "imputed_cells": [{"row_index": row, "spreadsheet_row": row + 2, "is_imputed": True} for row in rows],
                "missing_before": int(missing_mask.sum()), "missing_after": skipped}
    return df, predictions, metadata


def review(record, settings, check=None):
    """Compute a preview without mutating the current data or requiring approval."""
    return _run(record, settings, check)[2]


def apply(record, settings, check=None):
    settings = validate_settings(settings)
    if not settings["acknowledge"]:
        raise ValueError("Confirm that model-filled values are estimates before applying")
    df, predictions, metadata = _run(record, settings, check)
    result = df.copy(deep=True).astype({settings["target"]: object})
    for position, value in predictions.items():
        if not _empty(df.iloc[position][settings["target"]]):
            raise ValueError("The target cell changed while fitting; review the current revision again")
        result.at[df.index[position], settings["target"]] = value
    (check or (lambda: None))()
    return result, metadata

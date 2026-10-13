"""Explicit, deterministic estimates; observed cells are never overwritten."""

import math
import re
from collections import Counter

import numpy as np
import pandas as pd

from .common import missing, scalar
from .type_detector import BOOLEAN_MAP, detect_column_type

BASIC = (
    "mean",
    "median",
    "mode",
    "constant",
    "forward_fill",
    "backward_fill",
    "linear_interpolation",
)
GROUPED = (
    "group_mean",
    "group_median",
    "group_mode",
    "group_forward_fill",
    "group_backward_fill",
)
METHODS = ("preserve", *BASIC, *GROUPED)
ORDERED = (
    "forward_fill",
    "backward_fill",
    "linear_interpolation",
    "group_forward_fill",
    "group_backward_fill",
)
NUMERIC = ("mean", "median", "group_mean", "group_median", "linear_interpolation")
WARNINGS = {
    "mean": "Mean imputation reduces variance and can distort correlations; it assumes the observed mean is suitable for missing rows.",
    "median": "Median imputation can concentrate values at the median and distort distributions and correlations.",
    "mode": "Mode imputation increases the most frequent category and can distort category frequencies. Ties use the first observed value.",
    "constant": "A user-defined constant is a placeholder, not an observed fact. Zero and unknown are different meanings.",
    "forward_fill": "Assumes an observed value remains valid until the next observation within the same entity.",
    "backward_fill": "Uses a later observation; this can leak future information into historical analyses.",
    "linear_interpolation": "Assumes a linear relationship between observations over the ordering coordinate. Estimates are not verified facts.",
}


def number(value):
    """Reject labels, percentages, booleans, invalid/nonfinite numeric data."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("Boolean values are not numeric measurements")
    text = str(value).strip()
    if not re.fullmatch(
        r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text
    ):
        raise ValueError(
            "Numeric methods need plain numeric values. Approve an appropriate type/format conversion first; do not guess currency or percentage units."
        )
    result = float(text.replace(",", ""))
    if not math.isfinite(result):
        raise ValueError("Numeric values must be finite")
    return result


def distribution(series):
    values = [v for v in series if not missing(v)]
    frequencies = Counter(str(v) for v in values)
    numeric_values = []
    for value in values:
        try:
            numeric_values.append(number(value))
        except ValueError:
            pass
    stats = None
    if numeric_values and len(numeric_values) == len(values):
        sample = pd.Series(numeric_values, dtype=float)
        q1, q3 = sample.quantile([0.25, 0.75])
        spread = q3 - q1
        stats = {
            "count": len(sample),
            "mean": scalar(sample.mean()),
            "median": scalar(sample.median()),
            "std": scalar(sample.std()) if len(sample) > 1 else 0.0,
            "min": scalar(sample.min()),
            "max": scalar(sample.max()),
            "q1": scalar(q1),
            "q3": scalar(q3),
            "skewness": scalar(sample.skew()) if len(sample) >= 3 else None,
            "outlier_count": int(
                ((sample < q1 - 1.5 * spread) | (sample > q3 + 1.5 * spread)).sum()
            ),
        }
        stats = {
            k: (None if isinstance(v, float) and not math.isfinite(v) else v)
            for k, v in stats.items()
        }
    return {
        "numeric": stats,
        "frequencies": [
            {"value": value, "count": count}
            for value, count in frequencies.most_common(10)
        ],
        "distinct_categories": len(frequencies),
        "observed_count": len(values),
    }


def missing_pattern(series):
    mask = [missing(v) for v in series]
    runs, current = [], 0
    for item in mask:
        if item:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return {
        "missing_runs": len(runs),
        "longest_run": max(runs, default=0),
        "leading_missing": next((i for i, v in enumerate(mask) if not v), len(mask)),
        "trailing_missing": next(
            (i for i, v in enumerate(reversed(mask)) if not v), len(mask)
        ),
        "example_spreadsheet_rows": [i + 2 for i, v in enumerate(mask) if v][:20],
    }


def recommendation(series, kind):
    stats = distribution(series)
    available = [
        "preserve",
        "mode",
        "constant",
        "forward_fill",
        "backward_fill",
        "group_mode",
        "group_forward_fill",
        "group_backward_fill",
    ]
    if kind in ("integer", "decimal") and stats["numeric"]:
        available += [
            "mean",
            "median",
            "group_mean",
            "group_median",
            "linear_interpolation",
        ]
        numeric_stats = stats["numeric"]
        skew = numeric_stats["skewness"]
        robust = numeric_stats["outlier_count"] > 0 or (
            skew is not None and abs(skew) > 1
        )
        method = "median" if robust else "mean"
        reason = (
            "Skewness or IQR outliers favor a robust median."
            if robust
            else "The observed distribution has no strong detected skew or IQR outliers; the mean may be suitable. Small samples provide weak evidence."
        )
    elif not stats["observed_count"]:
        method, reason = (
            "constant",
            "No observed values are available. Only an explicitly chosen constant can fill this column.",
        )
        available = ["preserve", "constant"]
    else:
        method, reason = (
            "mode",
            "The most frequent observed value may be useful when one category is representative; otherwise choose a meaningful constant or leave missing values.",
        )
    if kind in ("integer", "decimal") and not stats["numeric"]:
        available += [
            "mean",
            "median",
            "group_mean",
            "group_median",
            "linear_interpolation",
        ]
        method = "constant"
        reason = "Some observed values are not plain finite numbers. Numeric methods are blocked until approved marker normalization or safe formatting conversions resolve them. Otherwise use a meaningful constant or leave gaps."
    return {
        "available_methods": available,
        "method": method,
        "explanation": reason,
        "warnings": [
            "Missing percentage alone cannot establish that missingness is random.",
            WARNINGS[method],
        ],
        "statistics": stats,
        "missing_pattern": missing_pattern(series),
        "conditional_suggestions": [
            "For known repeated entities, choose group median (numeric) or group mode, and select entity columns.",
            "For a known time series, select grouping and an explicit ordering column before choosing interpolation or directional fill.",
        ],
    }


def fill_mean(series):
    values = [number(v) for v in series if not missing(v)]
    return math.fsum(v / len(values) for v in values) if values else None


def fill_median(series):
    values = [number(v) for v in series if not missing(v)]
    return float(pd.Series(values).median()) if values else None


def fill_mode(series):
    values = [v for v in series if not missing(v)]
    if not values:
        return None
    keys = [(type(v).__name__, str(v)) for v in values]
    winner = Counter(keys).most_common(1)[0][0]
    return values[keys.index(winner)]


def ordered_coordinates(series):
    if any(missing(v) for v in series):
        raise ValueError(
            "Ordering values cannot be missing; resolve them before imputation"
        )
    try:
        values = [number(v) for v in series]
    except ValueError:
        if any(
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].*)?", str(v).strip())
            for v in series
        ):
            raise ValueError(
                "Ordering needs numeric coordinates or valid ISO dates. Approve safe date conversion first; ambiguous dates are blocked."
            )
        try:
            dates = pd.to_datetime(series, format="ISO8601", utc=True, errors="raise")
            values = list(dates.astype("int64"))
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Ordering contains invalid dates; correct them first")
    if len(values) != len(set(values)):
        raise ValueError("Ordering values must be unique within each group")
    return pd.Series(values, index=series.index)


def fill_forward(series):
    values = []
    previous = None
    for value in series:
        if not missing(value):
            previous = value
        values.append(previous)
    return pd.Series(values, index=series.index, dtype=object)


def fill_backward(series):
    return fill_forward(series.iloc[::-1]).iloc[::-1]


def fill_linear(series, coordinates):
    observed = series.notna()
    if observed.sum() < 2:
        return series.copy()
    origin = coordinates.iloc[0]
    x = np.array(
        [
            float(int(v) - int(origin))
            if isinstance(v, (int, np.integer))
            else float(v - origin)
            for v in coordinates
        ]
    )
    if not np.isfinite(x).all() or np.any(np.diff(x) <= 0):
        raise ValueError(
            "Ordering coordinates are too close or too large for reliable interpolation"
        )
    result = series.copy()
    inside = ~observed & (x >= x[observed][0]) & (x <= x[observed][-1])
    estimates = np.interp(x[inside], x[observed], series.loc[observed].astype(float))
    if not np.isfinite(estimates).all():
        raise ValueError(
            "Interpolation produced nonfinite estimates; review numeric ranges"
        )
    result.loc[inside] = estimates
    return result


def validate_parameters(method, parameters):
    if method not in METHODS:
        raise ValueError("Choose a supported imputation method")
    groups = parameters.get("group_by", [])
    if (
        not isinstance(groups, list)
        or len(groups) > 5
        or any(not isinstance(c, str) for c in groups)
        or len(groups) != len(set(groups))
    ):
        raise ValueError("Choose up to five distinct grouping columns")
    if parameters.get("order_by") is not None and not isinstance(
        parameters["order_by"], str
    ):
        raise ValueError("Choose a valid ordering column name")
    if isinstance(parameters.get("value"), (float, int)) and not math.isfinite(
        parameters["value"]
    ):
        raise ValueError("A constant must be finite")
    if method.startswith("group_") and not groups:
        raise ValueError("A grouped method requires grouping columns")
    if method in ORDERED:
        if (
            not isinstance(parameters.get("order_by"), str)
            or not parameters["order_by"]
        ):
            raise ValueError("Ordered imputation requires an ordering column")
        if not groups and parameters.get("single_entity") is not True:
            raise ValueError(
                "Select entity grouping columns or explicitly confirm a single related sequence"
            )
    for key in ("confirmed", "single_entity"):
        if key in parameters and not isinstance(parameters[key], bool):
            raise ValueError(f"{key} must be a boolean")
    if method == "constant" and (
        "value" not in parameters
        or not isinstance(parameters["value"], (str, int, float, bool))
        or missing(parameters["value"])
    ):
        raise ValueError(
            "Choose a non-missing constant; an unknown marker cannot fill missing data"
        )


def impute_missing_values(df, column, method, parameters):
    """Return a new DataFrame and audit detail. Callers control explicit approval."""
    validate_parameters(method, parameters)
    if column not in df:
        raise ValueError("Unknown imputation column")
    result = df.copy(deep=True)
    original = df[column]
    mask = original.map(missing)
    detail = {
        "method": method,
        "missing_before": int(mask.sum()),
        "missing_after": int(mask.sum()),
        "imputed_count": 0,
        "imputed_cells": [],
        "warnings": [],
        "failures": [],
        "group_by": parameters.get("group_by", []),
        "order_by": parameters.get("order_by"),
        "distribution_before": distribution(original),
        "distribution_after": distribution(original),
    }
    if method == "preserve":
        return result, detail
    base = method.removeprefix("group_")
    detail["warnings"] = [
        WARNINGS[base],
        "Imputed values are estimates or placeholders, not verified observations.",
    ]
    kind = detect_column_type(original)["type"]
    if method in NUMERIC:
        if not mask.all() and kind not in ("integer", "decimal"):
            raise ValueError(
                "Numeric imputation is limited to numeric measurements, not identifiers, currency labels, percentages, or mixed types. Review conversions first."
            )
        for v in original.loc[~mask]:
            number(
                v
            )  # Fail the entire operation if a dependency cannot be interpreted safely.
    groups = parameters.get("group_by", [])
    dependencies = groups + ([parameters["order_by"]] if method in ORDERED else [])
    if any(c not in df or c == column for c in dependencies):
        raise ValueError(
            "Grouping/ordering columns must exist and differ from the target column"
        )
    constant = parameters.get("value")
    if method == "constant":
        if kind in ("integer", "decimal"):
            constant = number(constant)
        elif kind in ("date", "datetime"):
            ordered_coordinates(pd.Series([constant]))
            if not re.match(r"\d{4}-\d{2}-\d{2}", str(constant)):
                raise ValueError("Date constants must be valid ISO dates")
        elif kind == "boolean":
            if str(constant).strip().lower() not in BOOLEAN_MAP:
                raise ValueError(
                    "Boolean constants must be recognizable true/false values"
                )
            constant = BOOLEAN_MAP[str(constant).strip().lower()]
        elif not isinstance(constant, str):
            constant = str(constant)
    eligible = pd.Series(True, index=df.index)
    for key in groups:
        eligible &= ~df[key].map(missing)
    skipped = int((mask & ~eligible).sum())
    if skipped:
        detail["warnings"].append(
            f"{skipped} missing cells have missing group keys and were left unchanged."
        )
    chunks = (
        [df.loc[eligible]]
        if not groups
        else [
            part
            for _, part in df.loc[eligible].groupby(groups, sort=False, dropna=False)
        ]
    )
    filled = original.astype(object).copy()
    empty_groups = 0
    for part in chunks:
        coordinates = None
        if method in ORDERED:
            coordinates = ordered_coordinates(part[parameters["order_by"]])
            indices = coordinates.sort_values(kind="stable").index
            coordinates = coordinates.loc[indices]
        else:
            indices = part.index
        series = original.loc[indices].astype(object).copy()
        local_mask = mask.loc[indices]
        series.loc[local_mask] = None
        if base in ("mean", "median", "mode", "constant"):
            value = (
                constant
                if base == "constant"
                else {"mean": fill_mean, "median": fill_median, "mode": fill_mode}[
                    base
                ](series)
            )
            if value is None:
                empty_groups += 1
                continue
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("The estimated value is not finite")
            filled.loc[indices[local_mask]] = value
        else:
            observed_positions = np.flatnonzero(~local_mask.to_numpy())
            if len(observed_positions) < (2 if base == "linear_interpolation" else 1):
                empty_groups += 1
                continue
            if base == "linear_interpolation":
                numeric_series = series.map(
                    lambda v: np.nan if missing(v) else number(v)
                )
                candidates = fill_linear(numeric_series, coordinates)
            else:
                candidates = (
                    fill_forward(series)
                    if base == "forward_fill"
                    else fill_backward(series)
                )
            # Do not extrapolate either end, even for directional fills.
            interior = pd.Series(False, index=indices)
            interior.iloc[observed_positions[0] : observed_positions[-1] + 1] = True
            to_fill = local_mask & interior & ~candidates.map(missing)
            filled.loc[indices[to_fill]] = candidates.loc[to_fill]
    if empty_groups:
        detail["warnings"].append(
            f"{empty_groups} groups/columns lacked sufficient observed values; those cells remain missing."
        )
    result[column] = filled
    imputed = mask & ~filled.map(missing)
    detail.update(
        missing_after=int(filled.map(missing).sum()),
        imputed_count=int(imputed.sum()),
        imputed_cells=[
            {
                "row_index": scalar(i),
                "spreadsheet_row": int(i) + 2
                if isinstance(i, (int, np.integer))
                else None,
                "is_imputed": True,
            }
            for i in df.index[imputed]
        ],
        distribution_after=distribution(filled),
    )
    if detail["missing_after"]:
        detail["warnings"].append(
            f"{detail['missing_after']} missing values remain. Boundary values are never extrapolated."
        )
    return result, detail

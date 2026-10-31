"""Explicit, deterministic estimates; observed cells are never overwritten."""

import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from .date_analyzer import parse_formatted_date, detect_date_pattern, DATE_OUTPUT_FORMATS, render_date

import numpy as np
import pandas as pd

from .common import missing, scalar, ACTIVE_SETTINGS
from .currency import parse_currency, SYMBOL_CODES
from .percentage import parse_percentage
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
METHODS = ("preserve", "date_sequence", *BASIC, *GROUPED)
ORDERED = (
    "date_sequence",
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


def numeric_candidate(series, kind):
    declared = ACTIVE_SETTINGS.get().get(str(series.name), {}).get("type")
    if declared and declared not in ("numeric", "salary", "currency", "percentage"):
        return False
    if kind in ("identifier", "phone", "boolean", "date", "datetime"):
        return False
    if kind in ("integer", "decimal", "currency", "number_with_symbol", "percentage"):
        return True
    if re.search(
        r"salary|wage|amount|price|cost|income|revenue|balance",
        str(series.name),
        re.IGNORECASE,
    ):
        return True
    values = [v for v in series if not missing(v)]
    valid = 0
    for value in values:
        try:
            number(value)
            valid += 1
        except ValueError:
            pass
    return bool(values and valid >= len(values) / 2)


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
    if numeric_candidate(series, kind) and stats["numeric"]:
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
    if (
        stats["observed_count"]
        and numeric_candidate(series, kind)
        and not stats["numeric"]
    ):
        available += [
            "mean",
            "median",
            "group_mean",
            "group_median",
            "linear_interpolation",
        ]
        method = "constant"
        reason = "Mean and median are available for this amount column, but some observed values are not plain finite numbers. Approve missing-marker normalization for placeholders and remove currency/unit labels using the formatting controls before numeric imputation. No currency conversion is performed; only combine amounts known to use the same unit. Unsupported values block the operation rather than being ignored."
    if kind in ("date", "datetime") and stats["observed_count"]:
        available += ["median", "group_median", "date_sequence"]
        reason = "Date median estimates the chronological middle date; it is not a verified event date. Ambiguous and invalid observed dates must be resolved first."
    if kind == "currency":
        reason = "Mean and median read numeric amounts directly from currency notation and fill only missing cells. Observed values keep their original formatting. Conflicting currency labels block calculation; no currency conversion is performed. Confirm bare amounts use the same currency."
    if kind == "percentage":
        reason = "Mean and median are available for percentage amounts. Values with % are calculated in percentage points. Mixed marked and bare numbers require explicit scale normalization first; observed cells are preserved."
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


def imputation_summary(original, filled, detail):
    """Summarize only values actually written, never a discarded full-column proposal."""
    mask = original.map(missing)
    imputed = mask & ~filled.map(missing)
    detail.update(missing_before=int(mask.sum()), missing_after=int(filled.map(missing).sum()),
        imputed_count=int(imputed.sum()),
        imputed_cells=[{"row_index":scalar(i),"spreadsheet_row":int(i)+2,"is_imputed":True} for i in original.index[imputed]],
        distribution_before=distribution(original), distribution_after=distribution(filled))
    return detail


def impute_missing_values(df, column, method, parameters):
    validate_parameters(method, parameters)
    if column not in df: raise ValueError("Unknown imputation column")
    groups = parameters.get("group_by", [])
    if not groups: return _impute_missing_values(df, column, method, parameters)
    if any(c not in df or c == column for c in groups): raise ValueError("Grouping columns must exist and differ from the target column")
    original = df[column]
    mask = original.map(missing)
    targets = mask & (df.index.isin(parameters["_target_rows"]) if "_target_rows" in parameters else True)
    eligible = pd.Series(True,index=df.index)
    for group in groups: eligible &= ~df[group].map(missing)
    result = df.copy(deep=True).astype({column:object})
    detail = {"method":method,"group_by":groups,"order_by":parameters.get("order_by"),"warnings":[],"failures":[],"excluded_estimates":0}
    output_formats = {}
    for labels, part in df.loc[eligible].groupby(groups,sort=False,dropna=False):
        if not targets.loc[part.index].any(): continue
        try:
            cleaned, summary = _impute_missing_values(part,column,method,{**parameters,"_column_kind":parameters.get("_column_kind") or detect_column_type(original)["type"]})
        except ValueError as exc:
            detail["failures"].append({"group":str(labels),"reason":str(exc)})
            detail["warnings"].append(f"Group {dict(zip(groups,labels if isinstance(labels,tuple) else (labels,)))} was left unchanged: {exc}")
            continue
        result.loc[part.index,column] = cleaned[column]
        detail["warnings"].extend(summary["warnings"])
        detail["excluded_estimates"] += summary.get("excluded_estimates",0)
        if summary.get("date_output_format"):
            for cell in summary["imputed_cells"]: output_formats[int(cell["row_index"])]=summary["date_output_format"]
    skipped=int((targets & ~eligible).sum())
    if skipped: detail["warnings"].append(f"{skipped} targeted cells have missing group keys and were left unchanged.")
    if output_formats: detail["date_output_formats"]=output_formats
    detail["warnings"]=list(dict.fromkeys(detail["warnings"]))
    summary=imputation_summary(original,result[column],detail)
    if summary["failures"] and not summary["imputed_count"]:
        raise ValueError(summary["failures"][0]["reason"])
    return result, summary


def _impute_missing_values(df, column, method, parameters):
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
    if method == "date_sequence":
        from .date_sequence import complete_date_sequence
        return complete_date_sequence(df, column, parameters)
    base = method.removeprefix("group_")
    detail["warnings"] = [
        WARNINGS[base],
        "Imputed values are estimates or placeholders, not verified observations.",
    ]
    kind = parameters.get("_column_kind") or detect_column_type(original)["type"]
    excluded = df.index.isin(parameters.get("_excluded_rows", []))
    source_mask = mask | excluded
    target_mask = mask & (df.index.isin(parameters["_target_rows"]) if "_target_rows" in parameters else True)
    detail["excluded_estimates"] = int((excluded & ~mask).sum())
    if detail["excluded_estimates"]: detail["warnings"].append(f"{detail['excluded_estimates']} previously imputed values were excluded from calculation sources.")
    calculation = original
    amount_marker = None
    percentage_marked = False
    if kind == "percentage" and base in ("mean", "median"):
        parsed_percentages = {}
        for index, value in original.loc[~source_mask].items():
            try:
                parsed_percentages[index] = parse_percentage(value)
            except ValueError as exc:
                raise ValueError(f"Column '{column}', spreadsheet row {int(index) + 2}, value {str(value)!r}: not a supported percentage.") from exc
        marked_states = {marked for _, marked in parsed_percentages.values()}
        if len(marked_states) > 1:
            index = next(index for index, (_, marked) in parsed_percentages.items() if not marked)
            raise ValueError(f"Column '{column}', spreadsheet row {int(index) + 2}, value {str(original.loc[index])!r}: percentage signs and bare numbers are mixed. Normalize the percentage scale before mean/median; choose whether bare numbers are percentage points or fractions.")
        percentage_marked = marked_states == {True}
        calculation = original.where(~source_mask).map(lambda value: None if missing(value) else float(parse_percentage(value)[0]))
        detail["warnings"].append("Percentage calculations preserve the existing scale and observed cells. Marked values use percentage points; no implicit multiplication or division by 100 is performed.")
    if kind == "currency" and base in ("mean", "median"):
        parsed = {}
        for index, value in original.loc[~source_mask].items():
            try:
                parsed[index] = parse_currency(value)
            except ValueError as exc:
                row = int(index) + 2 if isinstance(index, (int, np.integer)) else str(index)
                raise ValueError(
                    f"Column '{column}', spreadsheet row {row}, value {str(value)!r}: "
                    "not a supported currency amount. Correct this cell or explicitly mark it as missing before calculating."
                ) from exc
        markers = {SYMBOL_CODES.get(marker, marker) for _, marker in parsed.values() if marker}
        if len(markers) > 1:
            raise ValueError("Mean/median cannot combine different or ambiguous currency labels. Standardize a single known currency first; no exchange-rate conversion is performed.")
        amount_marker = next((marker for _, marker in parsed.values() if marker), None)
        calculation = original.where(~source_mask).map(lambda value: None if missing(value) else float(parse_currency(value)[0]))
        detail["warnings"].append("Calculations use numeric amounts in this column without currency conversion. Confirm that bare amounts and labelled amounts use the same currency. Observed cells are preserved.")
    date_median = kind in ("date", "datetime") and base == "median"
    parsed_dates = {}
    date_format = "YYYY-MM-DD"
    include_time = False
    date_zone = None
    if date_median:
        sources = parameters.get("_source_formats", {})
        formats = []
        awareness = set()
        for index, value in original.loc[~source_mask].items():
            try:
                parsed = parse_formatted_date(value, source_format=sources.get(int(index)))
                if not isinstance(parsed, datetime): parsed = datetime.combine(parsed, datetime.min.time())
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f"Column '{column}', spreadsheet row {int(index)+2}, value {str(value)!r}: resolve invalid or ambiguous dates before median imputation.") from exc
            aware = parsed.utcoffset() is not None
            awareness.add(aware)
            if aware and date_zone is None: date_zone = parsed.tzinfo
            include_time |= bool(parsed.time() != datetime.min.time() or re.search(r"[T ]\d{2}:\d{2}", str(value)))
            parsed_dates[index] = parsed
            pattern = sources.get(int(index)) or detect_date_pattern(value)
            if pattern in DATE_OUTPUT_FORMATS: formats.append(pattern)
        if len(awareness)>1: raise ValueError(f"Column '{column}': normalize mixed timezone-aware and timezone-naive dates before median imputation.")
        if formats: date_format = Counter(formats).most_common(1)[0][0]
        detail["date_output_format"] = date_format
        detail["warnings"].append(f"Date median is an estimated chronological midpoint. Date-only rounding policy: {parameters.get('date_rounding', 'floor')}. Observed dates are unchanged. Mixed or month-name formats use a supported numeric format.")
    if method in NUMERIC and not date_median:
        if not mask.all() and (
            kind
            in (
                "identifier",
                "phone",
                "boolean",
                "date",
                "datetime",
                "number_with_symbol",
            )
            or not numeric_candidate(original, kind)
        ):
            raise ValueError(
                "Numeric imputation is limited to numeric measurements, not identifiers, currency labels, percentages, or mixed types. Review conversions first."
            )
        for index, value in calculation.loc[~source_mask].items():
            try:
                number(value)
            except ValueError as exc:
                row = int(index) + 2 if isinstance(index, (int, np.integer)) else str(index)
                raise ValueError(
                    f"Column '{column}', spreadsheet row {row}, value {str(original.loc[index])!r}: {exc}"
                ) from exc
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
        series = calculation.loc[indices].astype(object).copy()
        local_mask = target_mask.loc[indices]
        donor_mask = source_mask.loc[indices]
        series.loc[donor_mask] = None
        if base in ("mean", "median", "mode", "constant"):
            if date_median:
                observed = [parsed_dates[index] for index in indices if index in parsed_dates]
                if not observed:
                    empty_groups += 1
                    continue
                epoch = datetime(1,1,1,tzinfo=timezone.utc) if date_zone else datetime(1,1,1)
                offsets = sorted(((value.astimezone(timezone.utc) if date_zone else value)-epoch)//timedelta(microseconds=1) for value in observed)
                midpoint = (offsets[(len(offsets)-1)//2]+offsets[len(offsets)//2])//2
                estimated = epoch+timedelta(microseconds=midpoint)
                if date_zone: estimated = estimated.astimezone(date_zone)
                if not include_time:
                    rounding = parameters.get("date_rounding", "floor")
                    if rounding not in ("floor","nearest","ceil"): raise ValueError("Choose floor, nearest or ceil for date rounding")
                    midnight=estimated.replace(hour=0,minute=0,second=0,microsecond=0)
                    remainder=estimated-midnight
                    if (rounding=="ceil" and remainder>timedelta(0)) or (rounding=="nearest" and remainder>=timedelta(hours=12)):
                        midnight += timedelta(days=1)
                    estimated=midnight
                    detail["date_rounding"]=rounding
                value = render_date(estimated, date_format, include_time)
            else:
                value = (
                    constant
                    if base == "constant"
                    else {"mean": fill_mean, "median": fill_median, "mode": fill_mode}[base](series)
                )
            if value is None:
                empty_groups += 1
                continue
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("The estimated value is not finite")
            if amount_marker and base in ("mean", "median"):
                value = f"{amount_marker}{value:.15g}" if amount_marker in ("$", "€", "£", "¥") else f"{value:.15g} {amount_marker}"
            elif percentage_marked and base in ("mean", "median"):
                value = f"{value:.15g}%"
            filled.loc[indices[local_mask]] = value
        else:
            observed_positions = np.flatnonzero(~donor_mask.to_numpy())
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
    imputation_summary(original, filled, detail)
    if detail["missing_after"]:
        detail["warnings"].append(
            f"{detail['missing_after']} missing values remain. Boundary values are never extrapolated."
        )
    return result, detail

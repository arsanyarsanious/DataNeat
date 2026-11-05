"""User-selected statistical checks. A rare observation is not inherently wrong."""
import hashlib
import json
import math

import numpy as np
import pandas as pd

from .common import missing, scalar
from .imputation import number

EMPTY = frozenset({""})


def validate_settings(settings):
    allowed = {"action", "column", "method", "multiplier", "group_by", "row_indices", "confirmed", "value"}
    if set(settings) - allowed:
        raise ValueError("Unknown outlier settings")
    result = {"action": settings.get("action", "review"), "column": settings.get("column", ""), "method": settings.get("method", "iqr"), "multiplier": settings.get("multiplier", 1.5), "group_by": settings.get("group_by", []), "row_indices": settings.get("row_indices"), "confirmed": settings.get("confirmed", False)}
    if result["action"] not in ("review", "save", "keep", "clear", "cap", "replace"):
        raise ValueError("Choose review, save, keep, clear, cap or replace")
    if not isinstance(result["column"], str) or not result["column"]:
        raise ValueError("Select a numeric measurement column")
    if result["method"] not in ("iqr", "mad"):
        raise ValueError("Choose IQR or MAD")
    if isinstance(result["multiplier"], bool) or not isinstance(result["multiplier"], (int, float)) or not math.isfinite(result["multiplier"]) or not .5 <= result["multiplier"] <= 20:
        raise ValueError("Outlier sensitivity must be between 0.5 and 20")
    groups = result["group_by"]
    if not isinstance(groups, list) or len(groups) > 3 or len(set(groups)) != len(groups) or any(not isinstance(v, str) for v in groups):
        raise ValueError("Choose up to three different grouping columns")
    indices = result["row_indices"]
    if indices is not None and (not isinstance(indices, list) or not indices or len(indices) > 100000 or any(type(v) is not int or v < 0 for v in indices)):
        raise ValueError("Select valid original row indices, or all flagged rows")
    if type(result["confirmed"]) is not bool:
        raise ValueError("Confirmation must be a boolean")
    if result["action"] == "replace":
        result["value"] = number(settings.get("value"))
    return result


def _signature(settings):
    return hashlib.sha256(json.dumps({key: settings[key] for key in ("column", "method", "multiplier", "group_by")}, sort_keys=True).encode()).hexdigest()


def review(record, settings, check=lambda: None):
    config = validate_settings(settings)
    df = record["editor_df"]
    column = config["column"]
    unknown = set([column, *config["group_by"]]) - set(df.columns)
    if unknown:
        raise ValueError("Unknown column: " + ", ".join(sorted(unknown)))
    if column in config["group_by"]:
        raise ValueError("The measurement cannot also be its grouping column")
    profile = next((c for c in record.get("editor_profile", record.get("profile", {})).get("columns", []) if c["column_name"] == column), {})
    declared = record.get("column_rules", {}).get(column, {})
    if declared.get("type") == "identifier" or profile.get("detected_type") in ("identifier", "phone", "boolean", "date", "datetime", "time", "duration", "currency", "percentage", "number_with_symbol"):
        raise ValueError(f'Column "{column}": choose an ordinary numeric measurement; identifiers, dates and labelled units are protected')
    values = {}
    for index, value in df[column].items():
        if len(values) % 256 == 0:
            check()
        if missing(value, EMPTY):
            continue
        try:
            values[int(index)] = number(value)
        except ValueError as exc:
            raise ValueError(f'Column "{column}", spreadsheet row {int(index)+2}, value "{value}": standardize this value before checking outliers') from exc
    # Estimates do not become the statistical evidence for another check.
    from .workflow import estimated_cells
    estimates = {row for name, row in estimated_cells(record) if name == column}
    signature = _signature(config)
    accepted = {(item["row_index"], item["value"]) for item in record.get("outlier_acceptances", []) if item.get("signature") == signature and item.get("column") == column}
    groups = {}
    skipped_group_rows = 0
    for index in values:
        key = tuple(str(df.at[index, name]) for name in config["group_by"])
        if any(missing(df.at[index, name], EMPTY) for name in config["group_by"]):
            skipped_group_rows += 1
            continue
        groups.setdefault(key, []).append(index)
    bounds, findings, warnings = [], [], []
    for key, indices in groups.items():
        check()
        observed = [values[index] for index in indices if index not in estimates]
        if len(observed) < 5:
            warnings.append(f'Group {" / ".join(key) or "Entire column"}: at least five observed measurements are needed; unchanged.')
            continue
        data = np.array(observed, dtype=float)
        if config["method"] == "iqr":
            q1, q3 = np.quantile(data, [.25, .75])
            lower, upper = q1 - config["multiplier"] * (q3 - q1), q3 + config["multiplier"] * (q3 - q1)
        else:
            median = float(np.median(data))
            mad = float(np.median(np.abs(data - median)))
            if mad == 0:
                warnings.append(f'Group {" / ".join(key) or "Entire column"}: MAD is zero; use IQR or an explicit range instead. No automatic bound was inferred.')
                continue
            lower, upper = median - config["multiplier"] * 1.4826 * mad, median + config["multiplier"] * 1.4826 * mad
        if not np.isfinite(lower) or not np.isfinite(upper):
            raise ValueError("Outlier bounds overflowed; rescale these measurements first")
        boundary = {"group": list(key), "observed_count": len(observed), "lower": float(lower), "upper": float(upper)}
        bounds.append(boundary)
        for index in indices:
            value = values[index]
            if lower <= value <= upper or (index, str(scalar(df.at[index, column]))) in accepted:
                continue
            findings.append({"row_index": index, "spreadsheet_row": index + 2, "column": column, "before": scalar(df.at[index, column]), "after": float(min(max(value, lower), upper)), "lower": float(lower), "upper": float(upper), "group": list(key), "kind": "outlier", "message": f"Outside your {config['method'].upper()} review bounds [{lower:g}, {upper:g}]. This is a review suggestion, not proof of an error."})
    if skipped_group_rows:
        warnings.append(f"{skipped_group_rows} rows have missing group keys and were not checked.")
    return {"column": column, "method": config["method"], "count": len(findings), "findings": findings[:200], "all_row_indices": [item["row_index"] for item in findings], "bounds": bounds[:100], "group_count": len(groups), "warnings": list(dict.fromkeys(warnings))[:30], "coverage": "All rows checked within eligible groups; the displayed sample is limited to 200 findings and 100 group bounds.", "signature": signature, "_findings": findings}


def apply(record, settings, check=lambda: None):
    config = validate_settings(settings)
    if config["action"] == "review":
        raise ValueError("Choose a reviewed outlier action")
    if config["action"] in ("clear", "cap", "replace") and not config["confirmed"]:
        raise ValueError("Confirm the reviewed outlier correction")
    detail = review(record, config, check)
    findings = detail.pop("_findings")
    selected = set(config["row_indices"]) if config["row_indices"] is not None else {item["row_index"] for item in findings}
    current = {item["row_index"] for item in findings}
    if config["action"] != "save" and (not selected or not selected.issubset(current)):
        raise ValueError("The selected rows no longer contain unreviewed outliers. Review this check again.")
    after = record["editor_df"].copy(deep=True).astype(object)
    if config["action"] == "save":
        record.setdefault("outlier_rules", {})[config["column"]] = {**config, "action": "review", "row_indices": None, "confirmed": False}
    else:
        for item in findings:
            check()
            if item["row_index"] not in selected:
                continue
            if config["action"] == "keep":
                record.setdefault("outlier_acceptances", []).append({"column": config["column"], "row_index": item["row_index"], "value": str(item["before"]), "signature": detail["signature"]})
            else:
                after.at[item["row_index"], config["column"]] = None if config["action"] == "clear" else config["value"] if config["action"] == "replace" else item["after"]
    detail.update(action=config["action"], affected_rows=0 if config["action"] == "save" else len(selected))
    return after, detail


def findings(record, check=lambda: None):
    result = []
    for config in record.get("outlier_rules", {}).values():
        try:
            result.extend(review(record, config, check)["_findings"])
        except ValueError:
            # Another reviewed edit may temporarily introduce a nonnumeric value.
            # Existing type checks surface it; a saved statistical check must not
            # prevent unrelated editing or make the whole sheet inaccessible.
            continue
    return result

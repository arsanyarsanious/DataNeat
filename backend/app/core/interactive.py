"""Conservative initial cleanup and paginated, per-cell issue annotations."""

import re
from collections import defaultdict

from .data_formats import FORMAT_ACTIONS, expand_structured
from .semantic_types import SEMANTIC_TYPES
from .clock_time import is_clock_time
from .duration import is_duration, format_duration
from .cleaner import apply_cleaning_plan
from .common import missing, scalar
from .currency import parse_currency
from .date_analyzer import is_ambiguous_numeric_date, is_valid_date
from .imputation import impute_missing_values
from .percentage import is_percentage_number, parse_percentage
from .phone import international_phone
from .profiler import profile_dataframe
from .issue_detector import capitalization_style
from .symbols import parse_numeric_symbol
from .type_detector import is_boolean, is_decimal


def prepare_original_preview(df):
    """Normalize missing markers and whitespace only; retain the original upload."""
    return df.astype(object).map(lambda value: None if missing(value) else re.sub(r"\s+", " ", value.strip()) if isinstance(value, str) else value), []


def basic_cleanup(df):
    operations = []
    for column in df.columns:
        operations.append(
            {
                "column": column,
                "operation": "trim_whitespace",
                "enabled": True,
                "parameters": {},
            }
        )
    cleaned, logs = apply_cleaning_plan(df, operations)
    report = profile_dataframe(cleaned)
    for c in report["columns"]:
        name, kind = c["column_name"], c["detected_type"]
        if kind in ("text", "category") and not re.search(
            r"email|url|notes|description|password|token|address", name, re.I
        ):
            variants = defaultdict(list)
            for value in cleaned[name]:
                if isinstance(value, str) and not missing(value):
                    variants[value.casefold()].append(value)
            mapping = {}
            for key, values in variants.items():
                # Preserve short established acronyms such as IT and HR.
                mapping[key] = next(
                    (v for v in values if v.isupper() and len(v) <= 5),
                    values[0].title(),
                )
            before = cleaned[name].copy()
            cleaned[name] = before.map(
                lambda v: mapping.get(v.casefold(), v) if isinstance(v, str) else v
            )
            logs.append(
                {
                    "operation": "normalize_capitalization",
                    "column": name,
                    "modified_values": sum(
                        str(a) != str(b) for a, b in zip(before, cleaned[name])
                    ),
                    "parameters": {"strategy": "title_with_acronym_preservation"},
                }
            )
        if kind in ("date", "datetime", "boolean", "integer", "decimal"):
            operation = (
                "normalize_dates"
                if kind in ("date", "datetime")
                else "normalize_boolean"
                if kind == "boolean"
                else "normalize_numeric"
            )
            cleaned, more = apply_cleaning_plan(
                cleaned,
                [
                    {
                        "column": name,
                        "operation": operation,
                        "enabled": True,
                        "parameters": {
                            "interpretation": "preserve",
                            "include_time": kind == "datetime",
                        },
                    }
                ],
            )
            logs.extend(more)
    return cleaned, logs


def annotate(df, report, part, columns=None):
    from .common import missing as base_missing, marker_set
    markers_by_column = {c["column_name"]: marker_set(c.get("markers")) for c in report["columns"]}
    def missing(value):
        return base_missing(value, markers_by_column.get(column))
    columns = list(df.columns) if columns is None else columns
    by_column = {c["column_name"]: c for c in report["columns"]}
    odd_rows = {c["column_name"]: {row for issue in c["issues"] if issue["issue"] == "odd_value" for row in issue.get("row_indices", [])} for c in report["columns"]}
    conflicts = {}
    for column in columns:
        variants = defaultdict(set)
        for value in df[column]:
            if isinstance(value, str) and not missing(value):
                variants[value.casefold()].add(value)
        conflicts[column] = {key for key, values in variants.items() if len(values) > 1}
    duplicates = set(df.index[df.duplicated()])
    column_kinds = {name: {item["issue"] for item in by_column[name]["issues"]} for name in columns}
    rows = []
    for index, row in zip(part.index, part[columns].itertuples(index=False, name=None)):
        cells = []
        for position, column in enumerate(columns):
            value, c = row[position], by_column[column]
            kinds = column_kinds[column]
            issues = []

            def add(kind, message):
                issues.append({"kind": kind, "message": message})

            if missing(value):
                add(
                    "missing",
                    "This value is missing. Enter a value or choose an explicit imputation estimate.",
                )
            else:
                for finding in c["issues"]:
                    if finding["issue"] in ("data_format", "invalid_data_format") and int(index) in finding.get("row_indices",[]):
                        add(finding["issue"], "This value needs an explicit format interpretation or conversion. Choose the input conventions and review the result." if finding["issue"]=="data_format" else "This value is invalid under the detected format. Correct it or use the format controls to specify the intended interpretation.")
                if c["detected_type"] == "time":
                    if not is_clock_time(value):
                        add("invalid_time", "Invalid clock time. Correct the hour, minutes or seconds; clock hours must be below 24, or 1–12 with AM/PM.")
                    elif "time_format" in kinds:
                        add("time", "Clock time formats are mixed. Choose 24-hour or 12-hour AM/PM notation; the time of day is preserved.")
                if c["detected_type"] == "duration":
                    if not is_duration(value):
                        add("invalid_duration", "Unrecognized elapsed duration. Enter a duration such as 00:45:00, PT45M or 45 min, or clear it. Invalid values are not guessed.")
                    elif str(value).strip() != format_duration(value):
                        add("duration", "This elapsed duration uses another notation. Standardize to hours:minutes:seconds; hours over 24 are preserved.")
                if "boolean_inconsistency" in kinds and is_boolean(value):
                    add("boolean", "Boolean labels are mixed. Standardize recognized values across this column to true/false; missing and invalid cells are preserved.")
                if index in odd_rows[column]:
                    add("odd_value", "This value differs from the dominant type in this column. Review it before correcting or clearing it; it may be legitimate.")
                if isinstance(value, str) and (
                    value != value.strip() or re.search(r"\s{2,}", value)
                ):
                    add(
                        "whitespace",
                        "This value has extra whitespace. Trim edges and repeated spaces.",
                    )
                if "invalid_dates" in kinds and not is_valid_date(value):
                    add(
                        "invalid_date",
                        "This is not a valid calendar date. Correct it manually or clear it.",
                    )
                elif c["detected_type"] in (
                    "date",
                    "datetime",
                ) and is_ambiguous_numeric_date(value):
                    add(
                        "ambiguous_date",
                        "Day/month order is ambiguous. Choose an interpretation explicitly.",
                    )
                if "date_format_inconsistency" in kinds and (is_valid_date(value) or is_ambiguous_numeric_date(value)):
                    add("date_format", "Date formats are mixed in this column. Standardize dates after confirming any ambiguous day/month order.")
                if c["detected_type"] not in SEMANTIC_TYPES | {"duration", "time"} and isinstance(value, str) and (value.casefold() in conflicts[column] or ("case_inconsistency" in kinds and capitalization_style(value))):
                    add(
                        "capitalization",
                        "Capitalization is inconsistent within this column. Review the intended style before changing it.",
                    )
                for issue, parser, kind in [
                    ("currency_inconsistency", parse_currency, "currency"),
                    ("percentage_inconsistency", parse_percentage, "percentage"),
                    ("symbol_inconsistency", parse_numeric_symbol, "symbol"),
                ]:
                    if issue in kinds:
                        try:
                            parser(value)
                            add(
                                kind,
                                "Column notation is mixed. Choose a uniform symbol and numeric format; units are not converted.",
                            )
                        except ValueError:
                            pass
                if c["detected_type"] == "phone":
                    if "phone_inconsistency" in kinds:
                        add(
                            "phone",
                            "Country-code or plus notation differs. Choose the intended country and format.",
                        )
                    try:
                        if not international_phone(value) and "invalid_phone" in kinds:
                            add(
                                "phone",
                                "This phone number needs review; enter a corrected value or confirm its country.",
                            )
                    except ValueError:
                        add(
                            "phone", "Unrecognized phone number; no digits are guessed."
                        )
                if "type_mismatch" in kinds:
                    check = (
                        is_boolean
                        if c["detected_type"] == "boolean"
                        else is_decimal
                        if c["detected_type"] in ("integer", "decimal", "currency")
                        else is_percentage_number
                        if c["detected_type"] == "percentage"
                        else None
                    )
                    if check and not check(value):
                        add(
                            "type",
                            "This value does not match the detected column type.",
                        )
                if (c["detected_type"] == "email" or (not c.get("intent", {}).get("type") and re.search(r"email", column, re.I))) and not re.fullmatch(
                    r"[^\s@]+@[^\s@]+\.[^\s@]+", str(value)
                ):
                    add(
                        "email",
                        "Email syntax is invalid. Enter a corrected address; delivery is not verified.",
                    )
            if index in duplicates:
                add(
                    "duplicate",
                    "This row duplicates an earlier row. Review before removing duplicate rows.",
                )
            cells.append(issues)
        rows.append(cells)
    return rows


def propose(df, body, cached_report=None):
    if body.scope == "issue_columns":
        raise ValueError("Cross-column issue corrections require the current interactive workflow")
    column = body.column
    if column not in df:
        raise ValueError("Unknown column")
    if body.row_index not in df.index:
        raise ValueError("The selected row no longer exists")
    if body.action == "expand_structured":
        if body.scope!="column": raise ValueError("Expanding lists/JSON applies to the entire column")
        result=expand_structured(df,column,body.parameters)
        changes=[{"row_index":int(i),"column":name,"before":None,"after":scalar(value)} for name in result.columns if name not in df for i,value in result[name].items() if not missing(value)]
        return result,{"changed_cells":len(changes),"examples":changes[:10],"warnings":["The original column is preserved. Nested objects/lists remain JSON in the new columns. Added columns are included in history and undo."],"imputation":None}
    if body.action == "replace":
        if body.scope not in ("cell", "matching", "invalid_dates", "issue", "values"):
            raise ValueError("Manual replacement applies only to the selected cell")
        result = df.copy(deep=True)
        result[column] = result[column].astype(object)
        if body.scope == "values":
            sources = set(body.parameters["source_values"])
            present = {v for v in df[column] if isinstance(v, str) and not missing(v)}
            if not sources.issubset(present) and not body.parameters.get("allow_absent_recipe_values"):
                raise ValueError("Some selected values no longer exist. Reopen Unify text values.")
            mask = df[column].map(lambda v: isinstance(v, str) and v in sources)
            result.loc[mask, column] = body.value
        elif body.scope == "issue":
            issue_kind = body.parameters.get("issue_kind")
            annotations = annotate(df, cached_report or profile_dataframe(df), df[[column]], columns=[column])
            affected = [index for index, row in zip(df.index, annotations) if any(issue["kind"] == issue_kind for issue in row[0])]
            if body.row_index not in affected:
                raise ValueError("The selected cell does not have this issue anymore")
            result.loc[affected, column] = body.value
        elif body.scope == "invalid_dates":
            if is_valid_date(df.loc[body.row_index, column]) or missing(df.loc[body.row_index, column]):
                raise ValueError("Select an invalid date cell before applying this scope")
            report = cached_report or profile_dataframe(df)
            kind = next(c["detected_type"] for c in report["columns"] if c["column_name"] == column)
            if kind not in ("date", "datetime"):
                raise ValueError("This scope requires a detected date column")
            mask = df[column].map(lambda value: not missing(value) and not is_valid_date(value))
            result.loc[mask, column] = body.value
        elif body.scope == "matching":
            selected = scalar(df.loc[body.row_index, column])
            mask = df[column].map(lambda v: type(scalar(v)) is type(selected) and scalar(v) == selected)
            result.loc[mask, column] = body.value
        else:
            result.loc[body.row_index, column] = body.value
        warnings = [
            "Manual values are not verified facts; remaining issues will be checked again."
        ]
        if body.scope == "values":
            warnings.append("Only the explicitly selected exact text values in this column are unified across all pages.")
        if body.scope == "matching":
            warnings.append("Replaces exact, case-sensitive matches in this column across all pages. Different values and other columns are preserved.")
        if body.scope == "invalid_dates":
            warnings.append("Replaces every invalid date in this column across all pages. Valid dates, ambiguous dates and missing cells are preserved.")
        if body.scope == "issue":
            warnings.append("Only cells with the selected issue in this column are replaced across all pages. Other cells are preserved.")
    else:
        params = {**body.parameters, "confirmed": True}
        if body.action == "impute_missing_values":
            config = next((c for c in (cached_report or {}).get("columns", []) if c["column_name"] == column), {})
            if config.get("detected_type"):
                params["_column_kind"] = config["detected_type"]
            if config.get("intent", {}).get("type") and params.get("method") in ("mean", "median", "group_mean", "group_median", "linear_interpolation") and config["detected_type"] not in ("integer", "decimal", "date", "datetime"):
                raise ValueError("This imputation method does not match your selected column data type.")
            if body.scope == "cell": params["_target_rows"] = [body.row_index]
            result, detail = impute_missing_values(
                df, column, params.get("method", "mode"), params
            )
            warnings = detail["warnings"]
        else:
            result, _ = apply_cleaning_plan(
                df.loc[[body.row_index]] if body.action in FORMAT_ACTIONS and body.scope=="cell" else df,
                [
                    {
                        "column": column,
                        "operation": body.action,
                        "enabled": True,
                        "parameters": params,
                    }
                ],
            )
            warnings = (
                [
                    "Currency and unit labels are changed without exchange-rate or unit conversion."
                ]
                if body.action in ("normalize_currency", "normalize_symbols")
                else []
            )
        if body.action in FORMAT_ACTIONS:
            warnings=["Interpretation follows your chosen settings. Unsupported values block this operation with their column and row; no partial conversion is committed."]
            if body.action=="normalize_number_format": warnings.append(f"Fractions are rounded to {params.get('fraction_digits',12)} decimal places. Long identifiers should remain text.")
            if body.action=="convert_units": warnings.append(f"Measurement values are converted and rounded to {params.get('decimal_places',6)} decimal places. This is not a currency conversion.")
        if body.scope == "cell":
            if body.action == "remove_duplicates":
                raise ValueError(
                    "Duplicate removal applies to the dataset; choose column scope"
                )
            value = result.loc[body.row_index, column]
            result = df.copy(deep=True)
            result[column] = result[column].astype(object)
            result.loc[body.row_index, column] = value
    if body.action == "remove_duplicates":
        warnings = [
            "This removes rows duplicated under the selected comparison columns. The first occurrence is kept; the original upload is retained."
        ]
    changes = []
    resulting_values = result[column].to_dict()
    for index, old_value in df[column].items():
        if index not in resulting_values:
            changes.append(
                {"row_index": int(index), "before": "Row", "after": "Removed"}
            )
        elif (str(old_value), type(old_value).__name__) != (
            str(resulting_values[index]),
            type(resulting_values[index]).__name__,
        ):
            changes.append(
                {
                    "row_index": int(index),
                    "before": scalar(old_value),
                    "after": scalar(resulting_values[index]),
                }
            )
    return result, {
        "changed_cells": len(changes),
        "examples": changes[:10],
        "warnings": warnings,
        "imputation": detail if body.action == "impute_missing_values" else None,
    }

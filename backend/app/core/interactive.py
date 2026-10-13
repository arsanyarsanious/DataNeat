"""Conservative initial cleanup and paginated, per-cell issue annotations."""

import re
from collections import defaultdict

from .cleaner import apply_cleaning_plan
from .common import missing, scalar
from .currency import parse_currency
from .date_analyzer import is_ambiguous_numeric_date, is_valid_date
from .imputation import impute_missing_values
from .percentage import is_percentage_number, parse_percentage
from .phone import international_phone
from .profiler import profile_dataframe
from .symbols import parse_numeric_symbol
from .type_detector import is_boolean, is_decimal


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


def annotate(df, report, part):
    by_column = {c["column_name"]: c for c in report["columns"]}
    conflicts = {}
    for column in df.columns:
        variants = defaultdict(set)
        for value in df[column]:
            if isinstance(value, str) and not missing(value):
                variants[value.casefold()].add(value)
        conflicts[column] = {key for key, values in variants.items() if len(values) > 1}
    duplicates = df.duplicated()
    rows = []
    for index, row in part.iterrows():
        cells = []
        for column in df.columns:
            value, c = row[column], by_column[column]
            kinds = {i["issue"] for i in c["issues"]}
            issues = []

            def add(kind, message):
                issues.append({"kind": kind, "message": message})

            if missing(value):
                add(
                    "missing",
                    "This value is missing. Enter a value or choose an explicit imputation estimate.",
                )
            else:
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
                if isinstance(value, str) and value.casefold() in conflicts[column]:
                    add(
                        "capitalization",
                        "Capitalization differs between matching values.",
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
                if re.search(r"email", column, re.I) and not re.fullmatch(
                    r"[^\s@]+@[^\s@]+\.[^\s@]+", str(value)
                ):
                    add(
                        "email",
                        "Email syntax is invalid. Enter a corrected address; delivery is not verified.",
                    )
            if duplicates.loc[index]:
                add(
                    "duplicate",
                    "This row duplicates an earlier row. Review before removing duplicate rows.",
                )
            cells.append(issues)
        rows.append(cells)
    return rows


def propose(df, body):
    column = body.column
    if column not in df:
        raise ValueError("Unknown column")
    if body.row_index not in df.index:
        raise ValueError("The selected row no longer exists")
    if body.action == "replace":
        if body.scope != "cell":
            raise ValueError("Manual replacement applies only to the selected cell")
        result = df.copy(deep=True)
        result[column] = result[column].astype(object)
        result.loc[body.row_index, column] = body.value
        warnings = [
            "Manual values are not verified facts; remaining issues will be checked again."
        ]
    else:
        params = {**body.parameters, "confirmed": True}
        if body.action == "impute_missing_values":
            result, detail = impute_missing_values(
                df, column, params.get("method", "mode"), params
            )
            warnings = detail["warnings"]
        else:
            result, _ = apply_cleaning_plan(
                df,
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
            "This removes complete duplicate rows across the dataset. The original upload is retained."
        ]
    changes = []
    for index in df.index:
        if index not in result.index:
            changes.append(
                {"row_index": int(index), "before": "Row", "after": "Removed"}
            )
        elif (str(df.loc[index, column]), type(df.loc[index, column]).__name__) != (
            str(result.loc[index, column]),
            type(result.loc[index, column]).__name__,
        ):
            changes.append(
                {
                    "row_index": int(index),
                    "before": scalar(df.loc[index, column]),
                    "after": scalar(result.loc[index, column]),
                }
            )
    return result, {
        "changed_cells": len(changes),
        "examples": changes[:10],
        "warnings": warnings,
    }

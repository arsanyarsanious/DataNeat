"""Require reviewed source values before any new missing-value filling decision."""
from collections import defaultdict

from .common import missing

ANALYSIS_SCHEMA_VERSION = 8
IMPUTATION_READINESS_POLICY = 1

LABELS = {
    "missing_marker": "Unresolved missing-value labels",
    "whitespace": "Extra whitespace",
    "capitalization": "Inconsistent capitalization",
    "invalid_date": "Invalid dates",
    "ambiguous_date": "Ambiguous dates",
    "date_format": "Mixed date formats",
    "type": "Values with the wrong type",
    "odd_value": "Values unlike the rest of the column",
    "email": "Invalid email addresses",
    "boolean": "Inconsistent boolean labels",
    "currency": "Mixed currency notation",
    "percentage": "Mixed percentage notation",
    "symbol": "Mixed numeric symbols or labels",
    "phone": "Phone issues",
    "duplicate": "Duplicate rows",
    "outlier": "Outliers awaiting review",
    "cross_column": "Cross-column rule violations",
    "data_format": "Data format interpretation",
    "invalid_data_format": "Invalid data format",
    "time": "Mixed clock formats",
    "invalid_time": "Invalid clock times",
    "duration": "Mixed duration formats",
    "invalid_duration": "Invalid durations",
    "rule_required": "Required values",
    "rule_type": "Values conflicting with the declared type",
    "rule_negative": "Negative values not allowed",
    "rule_unique": "Values required to be unique",
    "rule_allowed": "Values outside the allowed list",
    "rule_pattern": "Values outside the declared pattern",
    "rule_range": "Values outside the declared range",
    "rule_date_range": "Dates outside the declared range",
}


def actual_empty(value):
    """Marker text remains an observation until the user chooses to convert it."""
    return missing(value, markers=[""])


def column_letter(position):
    result = ""
    while position:
        position, remainder = divmod(position - 1, 26)
        result = chr(65 + remainder) + result
    return result


def readiness_from_annotations(record, column):
    """Pure reader used after profiling: never recursively request a new profile."""
    df = record["editor_df"]
    if column not in df:
        raise ValueError(f"Unknown column: {column}")
    by_kind = defaultdict(set)
    cells = record.get("workflow_annotations", {}).get(column, {})
    for index, flags in cells.items():
        if index not in df.index:
            continue
        for flag in flags:
            kind = flag["kind"]
            if kind in ("missing", "missing_values"):
                continue
            if kind == "rule_required" and actual_empty(df.at[index, column]):
                continue
            by_kind[kind].add(int(index))
    issues = [{"kind": kind, "label": LABELS.get(kind, kind.replace("_", " ").capitalize()),
               "count": len(indices), "example_rows": [index + 2 for index in sorted(indices)[:3]]}
              for kind, indices in sorted(by_kind.items())]
    count = sum(item["count"] for item in issues)
    message = "Only missing values remain, so this column is ready for imputation."
    if issues:
        rows = sorted(set().union(*by_kind.values()))
        letter = column_letter(list(df.columns).index(column) + 1)
        examples = ", ".join(f"{letter}{index + 2} (spreadsheet row {index + 2})" for index in rows[:3])
        summary = "; ".join(f"{item['label']}: {item['count']}" for item in issues)
        message = (f"Column '{column}': resolve other issues before filling missing values. "
                   f"{summary}. Example cells: {examples}. Correct, clear or explicitly accept "
                   "these findings first; only missing-value issues may remain.")
    return {"ready": not count, "blocking_count": count, "blocking_issues": issues, "message": message}


def column_readiness(record, column, check=lambda: None):
    if column not in record["editor_df"]:
        raise ValueError(f"Unknown column: {column}")
    if (record.get("_workflow_dirty") or record.get("analysis_schema_version") != ANALYSIS_SCHEMA_VERSION
            or column not in record.get("workflow_annotations", {}) or not record.get("editor_profile")):
        from .workflow import profile_record
        profile_record(record, check)
    check()
    return readiness_from_annotations(record, column)


def ensure_imputation_ready(record, column, check=lambda: None):
    readiness = column_readiness(record, column, check)
    if not readiness["ready"]:
        raise ValueError(readiness["message"])
    return readiness

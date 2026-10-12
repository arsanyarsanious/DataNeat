import re
from collections import defaultdict

from .common import missing
from .type_detector import is_boolean, is_date, is_decimal, is_integer


def issue(series, kind, values, **extra):
    return {
        "issue": kind,
        "column": str(series.name),
        "count": len(values),
        "examples": [str(v) for v in values[:5]],
        **extra,
    }


def detect_missing_values(series, markers=None):
    return issue(series, "missing_values", [v for v in series if missing(v, markers)])


def detect_whitespace_issues(series):
    return issue(
        series,
        "extra_whitespace",
        [
            v
            for v in series
            if isinstance(v, str) and (v != v.strip() or re.search(r"\s{2,}", v))
        ],
    )


def detect_case_inconsistency(series):
    groups = defaultdict(list)
    for v in series:
        if isinstance(v, str) and not missing(v):
            groups[v.strip().casefold()].append(v.strip())
    conflicts = [vs for vs in groups.values() if len(set(vs)) > 1]
    return issue(
        series,
        "case_inconsistency",
        [v for vs in conflicts for v in vs],
        conflicting_categories=len(conflicts),
    )


def detect_type_mismatches(series, detected_type):
    kind = (
        detected_type.get("type") if isinstance(detected_type, dict) else detected_type
    )
    check = {
        "boolean": is_boolean,
        "integer": is_integer,
        "decimal": is_decimal,
        "currency": is_decimal,
        "percentage": is_decimal,
        "date": is_date,
        "datetime": is_date,
    }.get(kind)
    return issue(
        series,
        "type_mismatch",
        [v for v in series if not missing(v) and check and not check(v)],
    )


def detect_column_issues(series, detected_type):
    return [
        v
        for v in [
            detect_missing_values(series),
            detect_whitespace_issues(series),
            detect_case_inconsistency(series),
            detect_type_mismatches(series, detected_type),
        ]
        if v["count"]
    ]


def detect_duplicates(df, subset=None):
    return int(df.duplicated(subset=subset).sum())

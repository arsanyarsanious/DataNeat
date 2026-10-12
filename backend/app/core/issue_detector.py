import re
from collections import defaultdict

from .common import missing
from .currency import analyze_currency_column
from .percentage import analyze_percentage_column, is_percentage_number
from .type_detector import is_boolean, is_decimal, is_integer


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
        "percentage": is_percentage_number,
    }.get(kind)
    return issue(
        series,
        "type_mismatch",
        [v for v in series if not missing(v) and check and not check(v)],
    )


def detect_currency_inconsistency(series):
    analysis = analyze_currency_column(series)
    return {
        "issue": "currency_inconsistency",
        "column": str(series.name),
        "count": analysis["affected_rows"] if analysis["inconsistent"] else 0,
        "examples": [str(v) for v in series if not missing(v)][:5],
        "formats": analysis["formats"],
        "explanation": "Currency labels and bare amounts are mixed. Choose a currency and explicitly confirm any unlabelled amounts before standardizing. No exchange-rate conversion is performed.",
    }


def detect_percentage_inconsistency(series):
    analysis = analyze_percentage_column(series)
    return {
        "issue": "percentage_inconsistency",
        "column": str(series.name),
        "count": analysis["affected_rows"] if analysis["inconsistent"] else 0,
        "formats": analysis["formats"],
        "examples": [
            str(v) for v in series if not missing(v) and is_percentage_number(v)
        ][:5],
    }


def detect_column_issues(series, detected_type):
    kind = (
        detected_type.get("type") if isinstance(detected_type, dict) else detected_type
    )
    return [
        v
        for v in [
            detect_missing_values(series),
            detect_whitespace_issues(series),
            detect_case_inconsistency(series),
            detect_type_mismatches(series, detected_type),
            *(
                [
                    detect_currency_inconsistency(series),
                    detect_percentage_inconsistency(series),
                ]
                if kind != "identifier"
                else []
            ),
        ]
        if v["count"]
    ]


def detect_duplicates(df, subset=None):
    return int(df.duplicated(subset=subset).sum())

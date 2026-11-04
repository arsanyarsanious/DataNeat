import re
from collections import defaultdict

from .clock_time import is_clock_time, clock_style
from .duration import is_duration, format_duration
from .semantic_types import SEMANTIC_TYPES, semantic_findings
from .common import missing, ACTIVE_SETTINGS
from .currency import analyze_currency_column, parse_currency
from .percentage import parse_percentage
from collections import Counter
from .percentage import analyze_percentage_column, is_percentage_number
from .phone import analyze_phone_column
from .symbols import analyze_symbols
from .type_detector import BOOLEAN_MAP, is_boolean, is_decimal, is_integer
from .date_analyzer import detect_date_pattern, is_valid_date, MONTH_FORMATS
from datetime import datetime


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


COMMON_ACRONYMS = {"IT", "HR", "USA", "UK", "UAE", "EU", "CEO", "CFO", "CTO", "ID", "USD", "EUR", "EGP"}


def capitalization_style(value):
    if not isinstance(value, str) or missing(value):
        return None
    text = value.strip()
    if text in COMMON_ACRONYMS or not any(char.isalpha() for char in text):
        return None
    if text.isupper():
        return "upper"
    if text.islower():
        return "lower"
    if text.istitle():
        return "title"
    return None


def detect_case_inconsistency(series):
    groups = defaultdict(list)
    for v in series:
        if isinstance(v, str) and not missing(v):
            groups[v.strip().casefold()].append(v.strip())
    conflicts = [vs for vs in groups.values() if len(set(vs)) > 1]
    conflict_keys = {vs[0].casefold() for vs in conflicts}
    styles = {capitalization_style(v) for v in series} - {None}
    mixed_styles = len(styles) > 1 and not re.search(r"email|url|notes|description|password|token|address", str(series.name), re.I)
    return issue(
        series,
        "case_inconsistency",
        [v for v in series if isinstance(v, str) and (v.strip().casefold() in conflict_keys or (mixed_styles and capitalization_style(v)))],
        conflicting_categories=len(conflicts),
    )


def detect_boolean_inconsistency(series):
    """Boolean meanings are valid even when their representations conflict."""
    families = {"true": "true_false", "false": "true_false",
                "yes": "yes_no", "no": "yes_no", "y": "y_n", "n": "y_n",
                "1": "one_zero", "0": "one_zero"}
    representations = defaultdict(set)
    used_families = set()
    recognized = []
    for value in series:
        if missing(value) or not is_boolean(value):
            continue
        text = str(value).strip()
        token = text.lower()
        representations[BOOLEAN_MAP[token]].add(text)
        used_families.add(families[token])
        recognized.append(value)
    inconsistent = len(used_families) > 1 or any(len(values) > 1 for values in representations.values())
    return issue(series, "boolean_inconsistency", recognized if inconsistent else [])


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


def detect_phone_issues(series):
    analysis = analyze_phone_column(series)
    result = []
    if analysis["inconsistent"]:
        result.append(
            {
                "issue": "phone_inconsistency",
                "column": str(series.name),
                "count": analysis["affected_rows"],
                "formats": analysis["formats"],
                "country_codes": analysis["country_codes"],
                "examples": [str(v) for v in series if not missing(v)][:5],
            }
        )
    if analysis["invalid_count"]:
        result.append(
            {
                "issue": "invalid_phone",
                "column": str(series.name),
                "count": analysis["invalid_count"],
                "examples": analysis["invalid_examples"],
            }
        )
    return result


def detect_symbol_inconsistency(series):
    analysis = analyze_symbols(series)
    return {
        "issue": "symbol_inconsistency",
        "column": str(series.name),
        "count": analysis["affected_rows"] if analysis["inconsistent"] else 0,
        "formats": analysis["formats"],
        "examples": [str(v) for v in series if not missing(v)][:5],
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
            *([] if kind in SEMANTIC_TYPES | {"duration", "time"} else [detect_case_inconsistency(series)]),
            *([issue(series, "duration_format", [v for v in series if not missing(v) and is_duration(v) and str(v).strip() != format_duration(v)]),
               issue(series, "invalid_duration", [v for v in series if not missing(v) and not is_duration(v)])] if kind == "duration" else []),
            *([issue(series, "time_format", [v for v in series if not missing(v) and is_clock_time(v)] if len({clock_style(v) for v in series if not missing(v) and is_clock_time(v)}) > 1 else []),
               issue(series, "invalid_time", [v for v in series if not missing(v) and not is_clock_time(v)])] if kind == "time" else []),
            *semantic_findings(series, kind),
            detect_type_mismatches(series, detected_type),
            *([issue(series, "invalid_email", [value for value in series if not missing(value) and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", str(value))])] if kind == "email" or (not ACTIVE_SETTINGS.get().get(str(series.name), {}).get("type") and re.search(r"email", str(series.name), re.I)) else []),
            *([detect_odd_values(series, kind)] if kind not in SEMANTIC_TYPES | {"identifier", "phone", "boolean", "duration", "time"} else []),
            *([detect_date_format_inconsistency(series)] if kind in ("date", "datetime") else []),
            *([detect_boolean_inconsistency(series)] if kind == "boolean" else []),
            *(detect_phone_issues(series) if kind == "phone" else []),
            *(
                [detect_symbol_inconsistency(series)]
                if kind == "number_with_symbol"
                else []
            ),
            *(
                [
                    detect_currency_inconsistency(series),
                    detect_percentage_inconsistency(series),
                ]
                if kind not in ("identifier", "phone") and (not ACTIVE_SETTINGS.get().get(str(series.name), {}).get("type") or kind in ("integer", "decimal", "currency", "percentage", "number_with_symbol"))
                else []
            ),
        ]
        if v["count"]
    ]


def detect_duplicates(df, subset=None):
    return int(df.duplicated(subset=subset).sum())


def value_family(value):
    if isinstance(value, bool):
        return "boolean"
    try:
        _, marked = parse_percentage(value)
        if marked:
            return "percentage"
    except ValueError:
        pass
    try:
        _, marker = parse_currency(value)
        return "currency" if marker else "numeric"
    except ValueError:
        pass
    if is_valid_date(value):
        return "date"
    return "text"


def detect_odd_values(series, kind=None):
    if kind == "percentage":
        odd = [(i, v) for i, v in series.items() if not missing(v) and not is_percentage_number(v)]
        return issue(series, "odd_value", [v for _, v in odd], row_indices=[int(i) for i, _ in odd], expected_type=kind)
    if kind in ('date', 'datetime'):
        odd = [(i, v) for i, v in series.items() if not missing(v) and not detect_date_pattern(v)]
        return issue(series, 'odd_value', [v for _, v in odd], row_indices=[int(i) for i, _ in odd], expected_type='date')
    observed = [(index, value, value_family(value)) for index, value in series.items() if not missing(value)]
    counts = Counter(family for _, _, family in observed)
    if len(observed) < 3 or not counts:
        return issue(series, "odd_value", [], row_indices=[], expected_type=None)
    # Bare numbers can share a currency/percentage column; scale ambiguity is checked separately.
    dominant, count = counts.most_common(1)[0]
    if dominant in ("currency", "percentage"):
        count += counts["numeric"]
    if count / len(observed) < .7:
        return issue(series, "odd_value", [], row_indices=[], expected_type=None)
    allowed = {dominant, "numeric"} if dominant in ("currency", "percentage") else {dominant}
    odd = [(index, value) for index, value, family in observed if family not in allowed]
    return issue(series, "odd_value", [value for _, value in odd], row_indices=[int(index) for index, _ in odd], expected_type=dominant)


def detect_date_format_inconsistency(series):
    formats = set()
    orders = set()
    values = []
    for value in series:
        if missing(value) or not is_valid_date(value):
            continue
        pattern = detect_date_pattern(value)
        values.append(value)
        if pattern == "Month-name formats":
            for fmt in MONTH_FORMATS:
                try:
                    datetime.strptime(str(value).strip(), fmt)
                    formats.add(fmt)
                    break
                except ValueError:
                    continue
        elif pattern and not pattern.startswith("YYYY") and "YYYY" in pattern:
            separator = "/" if "/" in pattern else "-"
            formats.add("numeric ending year " + separator)
            if "_or_" not in pattern:
                orders.add(pattern[:2])
        else:
            formats.add(pattern)
    return issue(series, "date_format_inconsistency", values if len(formats) > 1 or len(orders) > 1 else [], formats=sorted(str(fmt) for fmt in formats))

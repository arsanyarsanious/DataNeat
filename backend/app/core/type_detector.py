import re

from .common import missing, numeric
from .currency import currency_marker, parse_currency
from .date_analyzer import detect_date_pattern, is_valid_date

BOOLEAN_MAP = {
    "true": True,
    "yes": True,
    "y": True,
    "1": True,
    "false": False,
    "no": False,
    "n": False,
    "0": False,
}


def is_boolean(value):
    return str(value).strip().lower() in BOOLEAN_MAP


def is_integer(value):
    try:
        try:
            number = numeric(value)
        except ValueError:
            number = parse_currency(value)[0]
        return number == number.to_integral_value()
    except ValueError:
        return False


def is_decimal(value):
    try:
        try:
            numeric(value)
        except ValueError:
            parse_currency(value)
        return True
    except ValueError:
        return False


def is_date(value):
    return is_valid_date(value)


def detect_column_type(series, threshold=0.8):
    values = [v for v in series if not missing(v)]
    if not values:
        return {"type": "unknown", "match_score": 0.0}
    name = str(series.name or "").lower()
    strings = [str(v).strip() for v in values]
    if re.search(
        r"(^|[_\s])(id|identifier|code|zip|postal|phone|sku)($|[_\s])", name
    ) or any(re.fullmatch(r"0\d+", s) for s in strings):
        return {"type": "identifier", "match_score": 1.0}
    # Recognize the structure even when every date is impossible (e.g. 88-99-2089).
    date_shapes = sum(bool(detect_date_pattern(v)) for v in values) / len(values)
    if date_shapes >= threshold:
        kind = (
            "datetime"
            if all(detect_date_pattern(v) == "ISO datetime" for v in values)
            else "date"
        )
        return {
            "type": kind,
            "match_score": round(sum(is_date(v) for v in values) / len(values), 4),
        }
    if any(currency_marker(v) for v in values):
        amount_score = sum(
            is_decimal(v) and not str(v).strip().endswith("%") for v in values
        ) / len(values)
        if amount_score >= threshold or (
            re.search("salary|amount|price|cost", name) and amount_score >= 0.5
        ):
            return {"type": "currency", "match_score": round(amount_score, 4)}
    checks = []
    if any(
        s.lower() in {"yes", "no", "true", "false", "y", "n"} for s in strings
    ) or re.search(r"active|enabled|flag|is_", name):
        checks.append(("boolean", is_boolean))
    checks += [
        ("currency", lambda v: bool(re.match(r"^\s*[\$€£]", str(v))) and is_decimal(v)),
        ("percentage", lambda v: str(v).strip().endswith("%") and is_decimal(v)),
        ("datetime", lambda v: detect_date_pattern(v) == "ISO datetime" and is_date(v)),
        ("date", is_date),
        ("integer", is_integer),
        ("decimal", is_decimal),
    ]
    for kind, check in checks:
        score = sum(check(v) for v in values) / len(values)
        if score >= threshold:
            return {"type": kind, "match_score": round(score, 4)}
    # Date context and numeric context retain a useful conservative hypothesis for dirty columns.
    for kind, check, context in [
        (
            "date",
            lambda v: bool(detect_date_pattern(v)),
            bool(re.search("date|birth|joined", name)),
        ),
        ("decimal", is_decimal, bool(re.search("salary|amount|price|cost", name))),
    ]:
        score = sum(check(v) for v in values) / len(values)
        if context and score >= 0.5:
            return {"type": kind, "match_score": round(score, 4)}
    category = len(set(strings)) <= max(2, len(values) * 0.2)
    return {"type": "category" if category else "text", "match_score": 1.0}

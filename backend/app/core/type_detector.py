import re

from .semantic_types import detect_semantic
from .clock_time import is_clock_time
from .duration import is_duration
from .common import missing, numeric, ACTIVE_SETTINGS
from .currency import currency_marker, parse_currency
from .date_analyzer import detect_date_pattern, is_valid_date
from .percentage import parse_percentage
from .phone import international_phone, phone_hint, phone_text
from .symbols import parse_numeric_symbol

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


def declared_kind(settings):
    kind = settings.get("type", "")
    return {"numeric": "decimal", "salary": "decimal", "location": "category"}.get(kind, kind)


def detect_column_type(series, threshold=0.8):
    settings = ACTIVE_SETTINGS.get().get(str(series.name), {})
    if settings.get("type"):
        return {"type": declared_kind(settings), "match_score": 1.0}
    values = [v for v in series if not missing(v)]
    if not values:
        return {"type": "unknown", "match_score": 0.0}
    name = str(series.name or "").lower()
    strings = [str(v).strip() for v in values]
    if phone_hint(series.name):
        score = 0
        for value in values:
            try:
                phone_text(value)
                score += 1
            except ValueError:
                pass
        return {"type": "phone", "match_score": round(score / len(values), 4)}
    if re.search(r"(^|[_\s])(id|identifier|code|zip|postal|phone|sku)($|[_\s])", name):
        return {"type": "identifier", "match_score": 1.0}
    international_count = 0
    for value in values:
        try:
            if international_phone(value):
                international_count += 1
        except ValueError:
            pass
    if international_count / len(values) >= threshold:
        return {
            "type": "phone",
            "match_score": round(international_count / len(values), 4),
        }
    duration_context = bool(re.search(r"duration|elapsed|time_taken|processing_time", name))
    duration_score = sum(is_duration(v) for v in values) / len(values)
    explicit_duration = any(re.match(r"^P(?:T|\d)", s, re.I) or re.search(r"\d\s*(?:min(?:utes?)?|hrs?|hours?|sec(?:onds?)?)$", s, re.I) for s in strings)
    if (duration_context or explicit_duration) and duration_score >= (0.5 if duration_context else threshold):
        return {"type": "duration", "match_score": round(duration_score, 4)}
    clock_score = sum(is_clock_time(v) for v in values) / len(values)
    clock_context = bool(re.search(r"time|shift|clock", name)) and not duration_context
    if not duration_context and clock_score >= (0.5 if clock_context else threshold):
        return {"type": "time", "match_score": round(clock_score, 4)}
    semantic = detect_semantic(series, threshold)
    if semantic: return semantic
    # Recognize the structure even when every date is impossible (e.g. 88-99-2089).
    date_shapes = sum(bool(detect_date_pattern(v)) for v in values) / len(values)
    if date_shapes >= threshold:
        kind = (
            "datetime"
            if all(str(detect_date_pattern(v)).endswith("datetime") for v in values)
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
    percent_values = []
    for value in values:
        try:
            percent_values.append(parse_percentage(value)[1])
        except ValueError:
            pass
    percent_score = len(percent_values) / len(values)
    percent_name = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(series.name or "")).lower()
    percent_context = bool(
        re.search(
            r"(^|[_\s])(percent(?:age)?|ratio|discount|rate)($|[_\s])", percent_name
        )
    )
    if (
        percent_values
        and (any(percent_values) or percent_context)
        and (percent_score >= threshold or (percent_context and percent_score >= 0.5))
    ):
        return {"type": "percentage", "match_score": round(percent_score, 4)}
    symbol_matches = 0
    symbol_present = False
    for value in values:
        try:
            _, token, _ = parse_numeric_symbol(value)
            symbol_matches += 1
            symbol_present = symbol_present or bool(token)
        except ValueError:
            pass
    if symbol_present and symbol_matches / len(values) >= threshold:
        return {
            "type": "number_with_symbol",
            "match_score": round(symbol_matches / len(values), 4),
        }
    if any(re.fullmatch(r"0\d+", s) for s in strings):
        return {"type": "identifier", "match_score": 1.0}
    checks = []
    if any(
        s.lower() in {"yes", "no", "true", "false", "y", "n"} for s in strings
    ) or re.search(r"active|enabled|flag|is_", name):
        checks.append(("boolean", is_boolean))
    checks += [
        ("currency", lambda v: bool(re.match(r"^\s*[\$€£]", str(v))) and is_decimal(v)),
        ("percentage", lambda v: str(v).strip().endswith("%") and is_decimal(v)),
        ("datetime", lambda v: str(detect_date_pattern(v)).endswith("datetime") and is_date(v)),
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

"""Elapsed durations, deliberately separate from calendar dates and clock times."""
import re
from decimal import Decimal

from .common import missing


def parse_duration(value):
    text = str(value).strip()
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", text)
    if match:
        h, m, s = map(Decimal, match.groups())
        if m >= 60 or s >= 60:
            raise ValueError("Minutes and seconds must be below 60")
        return h * 3600 + m * 60 + s
    match = re.fullmatch(r"P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?", text, re.I)
    if match and any(match.groups()) and not text.upper().endswith('T'):
        return sum((Decimal(v or '0') * unit for v, unit in zip(match.groups(), [86400, 3600, 60, 1])), Decimal(0))
    component = r"(\d+(?:\.\d+)?)\s*(days?|hours?|hrs?|minutes?|mins?|seconds?|secs?|[dhms])"
    # Consume the entire input: never silently discard unknown suffixes or signs.
    # Accept spaces, commas, 'and', and compact forms such as 1d3h30m.
    separator = r"\s*(?:(?:,\s*)?(?:and\s+)|,\s*)?"
    if re.fullmatch(rf"{component}(?:{separator}{component})*", text, re.I):
        total = Decimal(0)
        for match in re.finditer(component, text, re.I):
            amount, unit = match.groups()
            multiplier = 86400 if unit.lower().startswith('d') else 3600 if unit.lower().startswith('h') else 60 if unit.lower().startswith('m') else 1
            total += Decimal(amount) * multiplier
        return total
    raise ValueError("Not a supported nonnegative elapsed duration")


def is_duration(value):
    try:
        parse_duration(value)
        return True
    except ValueError:
        return False


def format_duration(value):
    total = parse_duration(value)
    hours = int(total // 3600)
    minutes = int(total % 3600 // 60)
    seconds = total % 60
    sec = format(seconds, 'f').rstrip('0').rstrip('.') if seconds % 1 else str(int(seconds))
    if seconds < 10:
        sec = '0' + sec
    return f"{hours:02d}:{minutes:02d}:{sec}"


def normalize_durations(series):
    def convert(value):
        if missing(value):
            return value
        try:
            return format_duration(value)
        except ValueError:
            return value  # Invalid/ambiguous inputs require a manual decision.
    return series.map(convert)

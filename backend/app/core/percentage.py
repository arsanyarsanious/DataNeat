"""Explicit percentage notation and scale, without guessing bare-number meaning."""

import re
from collections import Counter
from decimal import Decimal, localcontext

from .common import missing

PATTERN = re.compile(r"([+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+))\s*(%)?")


def parse_percentage(value):
    match = PATTERN.fullmatch(str(value).strip())
    if not match:
        raise ValueError("Not a supported percentage or ratio")
    return Decimal(match[1].replace(",", "")), bool(match[2])


def is_percentage_number(value):
    try:
        parse_percentage(value)
        return True
    except ValueError:
        return False


def analyze_percentage_column(series):
    formats = Counter()
    for value in series:
        if missing(value):
            continue
        try:
            _, marked = parse_percentage(value)
            formats["with %" if marked else "without %"] += 1
        except ValueError:
            pass
    return {
        "formats": dict(formats),
        "inconsistent": bool(formats["with %"] and formats["without %"]),
        "affected_rows": sum(formats.values()),
    }


def normalize_percentage(series, settings):
    action = settings.get("action", "legacy")
    if action == "preserve":
        return series.copy(deep=True)
    if action in ("add", "remove"):

        def notation(value):
            if missing(value):
                return value
            match = PATTERN.fullmatch(str(value).strip())
            if not match:
                return value
            # Literal notation only: keep the numeric text, including its scale and zeros.
            return match[1] + ("%" if action == "add" else "")

        return series.map(notation)
    if action != "legacy":
        raise ValueError("Choose add, remove, or no change")
    output = settings.get("format", "with_sign")
    interpretation = settings.get("bare_interpretation", "preserve")
    if output not in ("with_sign", "without_sign", "ratio") or interpretation not in (
        "preserve",
        "percentage_points",
        "fraction",
    ):
        raise ValueError(
            "Choose a valid percentage output and bare-number interpretation"
        )

    def convert(value):
        if missing(value):
            return value
        try:
            number, marked = parse_percentage(value)
        except ValueError:
            return value
        if not marked and interpretation == "preserve":
            return value
        # A finite decimal is scaled exactly, even beyond the default Decimal precision.
        with localcontext() as context:
            context.prec = max(28, len(number.as_tuple().digits) + 4)
            points = (
                number
                if marked or interpretation == "percentage_points"
                else number * 100
            )
            result = points / 100 if output == "ratio" else points
            text = format(result, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text + "%" if output == "with_sign" else text

    return series.map(convert)

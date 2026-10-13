"""Recognize currency notation without assuming bare amounts have a currency."""

import re
from collections import Counter

from .common import missing, numeric

CURRENCY_CODES = (
    "USD",
    "EUR",
    "GBP",
    "EGP",
    "SAR",
    "AED",
    "CAD",
    "AUD",
    "JPY",
    "CNY",
    "INR",
    "CHF",
    "NZD",
    "ZAR",
    "KWD",
    "QAR",
    "BHD",
    "OMR",
    "TRY",
    "SEK",
    "NOK",
    "DKK",
    "BRL",
    "MXN",
    "SGD",
    "HKD",
    "KRW",
)
SYMBOL_CODES = {"€": "EUR", "£": "GBP"}
TOKENS = "|".join(re.escape(v) for v in ("$", "€", "£", "¥", *CURRENCY_CODES))
NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def parse_currency(value):
    text = str(value).strip()
    marker, number = None, text
    prefix = re.fullmatch(rf"({TOKENS})\s*({NUMBER})", text, re.IGNORECASE)
    suffix = re.fullmatch(rf"({NUMBER})\s*({TOKENS})", text, re.IGNORECASE)
    if prefix:
        marker, number = prefix.groups()
    elif suffix:
        number, marker = suffix.groups()
    if not re.fullmatch(NUMBER, number):
        raise ValueError("Not a supported currency amount")
    return numeric(number), marker.upper() if marker else None


def currency_marker(value):
    try:
        return parse_currency(value)[1]
    except ValueError:
        return None


def analyze_currency_column(series):
    formats = Counter()
    grouping = set()
    for value in series:
        if missing(value):
            continue
        try:
            _, marker = parse_currency(value)
            formats[marker or "bare number"] += 1
            grouping.add("," in str(value))
        except ValueError:
            pass
    labelled = sum(
        count for marker, count in formats.items() if marker != "bare number"
    )
    return {
        "formats": dict(formats),
        "labelled_count": labelled,
        "unlabelled_count": formats.get("bare number", 0),
        "inconsistent": bool(labelled and (len(formats) > 1 or len(grouping) > 1)),
        "affected_rows": sum(formats.values()),
    }


def normalize_currency(series, settings):
    action = settings.get("action", "legacy")
    if action in ("preserve", "add", "remove"):
        from .symbols import normalize_symbols

        if action == "preserve":
            return series.copy(deep=True)
        grouping = settings.get("grouping", "remove")
        if grouping not in ("add", "remove"):
            raise ValueError("Choose whether to include or remove commas")
        from .symbols import parse_numeric_symbol

        def format_number(value):
            if missing(value):
                return value
            try:
                number, _, _ = parse_numeric_symbol(value)
            except ValueError:
                return value
            number = number.replace(",", "")
            if grouping == "add":
                integer, dot, decimal = number.partition(".")
                sign = integer[:1] if integer[:1] in ("+", "-") else ""
                digits = integer[len(sign) :]
                integer = sign + re.sub(r"(?<=\d)(?=(\d{3})+$)", ",", digits)
                number = integer + dot + decimal
            return number

        formatted = series.map(format_number)
        return normalize_symbols(formatted, settings)
    if action != "legacy":
        raise ValueError("Choose add, remove, or no change")
    target = settings.get("currency", "")
    if target not in CURRENCY_CODES:
        raise ValueError("Choose a supported target currency")
    assumption = settings.get("assume_unlabelled", False)
    output = settings.get("format", "code")
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(target)
    if output not in ("code", "number", "symbol") or (
        output == "symbol" and not symbol
    ):
        raise ValueError("Choose a supported currency output format")
    # $ and ¥ have multiple meanings. They are only assigned when explicitly approved.
    approved_symbols = settings.get("symbol_aliases", [])
    if (
        not isinstance(assumption, bool)
        or not isinstance(approved_symbols, list)
        or any(v not in ("$", "¥") for v in approved_symbols)
    ):
        raise ValueError("Currency assumptions must be explicitly approved")
    if "$" in approved_symbols and target not in (
        "USD",
        "CAD",
        "AUD",
        "NZD",
        "SGD",
        "HKD",
    ):
        raise ValueError("$ must refer to a dollar currency")
    if "¥" in approved_symbols and target not in ("JPY", "CNY"):
        raise ValueError("¥ must refer to JPY or CNY")

    def convert(value):
        if missing(value):
            return value
        try:
            amount, marker = parse_currency(value)
        except ValueError:
            return value
        if marker is None:
            if not assumption:
                return value
        elif marker != target and SYMBOL_CODES.get(marker) != target:
            if marker not in approved_symbols:
                return value  # Never relabel or convert another currency.
        number = format(amount, "f")
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        return (
            number
            if output == "number"
            else f"{symbol}{number}"
            if output == "symbol"
            else f"{target} {number}"
        )

    return series.map(convert)

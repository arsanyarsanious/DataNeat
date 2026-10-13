"""Literal numeric affixes: change notation without rescaling or currency conversion."""

import re
from collections import Counter

from .common import missing

NUMBER = r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
TOKEN = r"[^\d\s+\-.,]{1,12}"


def parse_numeric_symbol(value):
    text = str(value).strip()
    if re.fullmatch(NUMBER, text):
        return text, None, None
    before = re.fullmatch(rf"({TOKEN})\s*({NUMBER})", text)
    after = re.fullmatch(rf"({NUMBER})\s*({TOKEN})", text)
    if before:
        token, number = before.groups()
        position = "prefix"
    elif after:
        number, token = after.groups()
        position = "suffix"
    else:
        raise ValueError("Not a number with a supported symbol")
    if "%" in token:
        raise ValueError("Percentages use percentage controls")
    return number, token, position


def analyze_symbols(series):
    formats = Counter()
    for value in series:
        if missing(value):
            continue
        try:
            _, token, _ = parse_numeric_symbol(value)
            formats[token or "no symbol"] += 1
        except ValueError:
            pass
    return {
        "formats": dict(formats),
        "inconsistent": len(formats) > 1
        and any(token != "no symbol" for token in formats),
        "has_symbols": any(token != "no symbol" for token in formats),
        "affected_rows": sum(formats.values()),
    }


def normalize_symbols(series, settings):
    action = settings.get("action", "preserve")
    if action == "preserve":
        return series.copy(deep=True)
    if action not in ("add", "remove"):
        raise ValueError("Choose add, remove, or no change")
    symbol = (
        settings.get("symbol", "").strip()
        if isinstance(settings.get("symbol", ""), str)
        else ""
    )
    position = settings.get("position", "prefix")
    if action == "add" and (
        not symbol or len(symbol) > 12 or re.search(r"[\d\s\x00-\x1f]", symbol)
    ):
        raise ValueError("Enter a short symbol or label without digits or spaces")
    if position not in ("prefix", "suffix"):
        raise ValueError("Choose prefix or suffix")

    def convert(value):
        if missing(value):
            return value
        try:
            number, _, _ = parse_numeric_symbol(value)
        except ValueError:
            return value
        if action == "remove":
            return number
        separator = " " if symbol.isalpha() else ""
        return (
            symbol + separator + number
            if position == "prefix"
            else number + separator + symbol
        )

    return series.map(convert)

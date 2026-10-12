"""Offline phone formatting; a region is required to interpret local numbers."""

import re
from collections import Counter
from numbers import Real

import phonenumbers as pn

from .common import missing

REGIONS = sorted(pn.SUPPORTED_REGIONS)


def phone_hint(name):
    words = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(name or "")).lower()
    return bool(
        re.search(
            r"(^|[_\s])(phone|telephone|tel|mobile|cell|whatsapp|contact_number)($|[_\s])",
            words,
        )
    )


def phone_text(value):
    if isinstance(value, Real) and not isinstance(value, bool):
        if value != int(value):
            raise ValueError("A phone number cannot be fractional")
        text = str(int(value))
    else:
        text = str(value).strip()
    # CSV formula-safe exports may carry Excel's text-escape apostrophe.
    # Recognize it for parsing, but preserve the stored value in no-change mode.
    if text.startswith("' +"):
        text = text[2:]
    elif text.startswith("'+"):
        text = text[1:]
    if not re.fullmatch(r"\+?[\d\s().-]+", text):
        raise ValueError("Unsupported phone number")
    digits = pn.normalize_digits_only(text)
    if not 7 <= len(digits) <= 17:
        raise ValueError("Unsupported phone number length")
    return text, digits


def international_phone(value):
    text, digits = phone_text(value)
    if text.startswith("+"):
        source = "with +"
        candidate = "+" + digits
    elif digits.startswith("00"):
        source = "with 00"
        candidate = "+" + digits[2:]
    else:
        return None
    try:
        number = pn.parse(candidate, None)
    except pn.NumberParseException:
        raise ValueError("Unrecognized country code")
    if not pn.is_possible_number(number):
        raise ValueError("Implausible phone number length")
    return number, source


def analyze_phone_column(series):
    explicit = []
    invalid = []
    for value in series:
        if missing(value):
            continue
        try:
            parsed = international_phone(value)
            if parsed:
                explicit.append(parsed[0].country_code)
        except ValueError:
            invalid.append(str(value))
    codes = set(explicit)
    formats = Counter()
    country_codes = Counter()
    for value in series:
        if missing(value):
            continue
        try:
            parsed = international_phone(value)
            if parsed:
                number, source = parsed
            else:
                _, digits = phone_text(value)
                candidates = []
                for code in codes:
                    if digits.startswith(str(code)):
                        try:
                            candidate = pn.parse("+" + digits, None)
                            if candidate.country_code == code and pn.is_possible_number(
                                candidate
                            ):
                                candidates.append(candidate)
                        except pn.NumberParseException:
                            pass
                number = candidates[0] if len(candidates) == 1 else None
                source = (
                    "country code without +" if number else "local / country unknown"
                )
            formats[source] += 1
            if number:
                country_codes[str(number.country_code)] += 1
        except ValueError:
            pass
    return {
        "formats": dict(formats),
        "country_codes": dict(country_codes),
        "inconsistent": len(formats) > 1,
        "invalid_count": len(invalid),
        "invalid_examples": invalid[:5],
        "affected_rows": sum(formats.values()),
    }


def parse_phone(value, region=None):
    explicit = international_phone(value)
    if explicit:
        return explicit[0]
    _, digits = phone_text(value)
    if not region:
        raise ValueError("Choose the country for local or unprefixed phone numbers")
    # Country metadata distinguishes a local prefix from a bare calling code.
    # For example, Italian local 3912345678 must not lose its initial 39.
    try:
        number = pn.parse(digits, region)
    except pn.NumberParseException:
        raise ValueError("Unrecognized phone number")
    if not pn.is_possible_number(number):
        raise ValueError("Implausible phone number length")
    return number


def normalize_phone(series, settings):
    action = settings.get("action", "preserve")
    if action == "preserve":
        return series.copy(deep=True)
    if action not in (
        "international",
        "international_digits",
        "national",
        "remove_plus",
        "add_plus",
    ):
        raise ValueError("Choose a supported phone format")
    region = settings.get("region") or None
    if action != "remove_plus" and region and region not in REGIONS:
        raise ValueError("Choose a supported phone country")
    if action in ("international", "international_digits") and not region:
        # Required even if existing rows are international: country choice is explicit for bare rows.
        raise ValueError("Choose the country used for local phone numbers")

    def convert(value):
        if missing(value):
            return value
        if action == "remove_plus":
            try:
                text, _ = phone_text(value)
            except ValueError:
                return value
            return text.removeprefix("+") if text.startswith("+") else value
        try:
            number = parse_phone(value, region)
        except ValueError:
            return value  # Never invent missing country codes or damage invalid rows.
        if action == "national":
            return pn.normalize_digits_only(
                pn.format_number(number, pn.PhoneNumberFormat.NATIONAL)
            )
        formatted = pn.format_number(number, pn.PhoneNumberFormat.E164)
        return formatted[1:] if action == "international_digits" else formatted

    return series.map(convert)

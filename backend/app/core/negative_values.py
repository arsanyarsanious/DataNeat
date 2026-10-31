"""Explicit, user-approved sign corrections without changing units or scale."""
import re
from decimal import Decimal
from .common import missing, numeric
from .currency import parse_currency
from .percentage import parse_percentage
from .symbols import parse_numeric_symbol


def unit_amount(text):
    number, token, position = parse_numeric_symbol(text)
    if position == 'prefix' and token and token.isalpha() and not re.match(r'\S+\s+', text):
        raise ValueError('An attached alphabetic prefix may be an identifier')
    return Decimal(number.replace(',', ''))


def signed_amount(value):
    text = str(value).strip().replace('\u2212', '-')
    if re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text):
        result = Decimal(text)
        if result.is_finite():
            return result
    for parser in (numeric, lambda v: parse_currency(v)[0], lambda v: parse_percentage(v)[0], unit_amount):
        try:
            return parser(text)
        except ValueError:
            pass
    raise ValueError('Not a supported signed numeric value')


def is_negative(value):
    if missing(value):
        return False
    try:
        return signed_amount(value) < 0
    except ValueError:
        return False


def absolute_values(series):
    def convert(value):
        if not is_negative(value):
            return value
        if isinstance(value, str):
            # Parsing above confirms the sign belongs to the amount. Keep its
            # unit, decimal precision, grouping and exponent exactly as entered.
            return re.sub(r'[-\u2212]', '', value, count=1)
        return abs(value)
    return series.map(convert)

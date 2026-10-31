"""Time of day without an invented date, duration, or timezone."""
import re
from decimal import Decimal
from .common import missing


def parse_clock_time(value):
    text = str(value).strip()
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2})(?::(\d{2}(?:\.\d+)?))?)?\s*([ap]\.?(?:m)\.?)?", text, re.I)
    if not match:
        raise ValueError("Enter a clock time such as 14:30 or 2:30 PM")
    hour, minute, second, meridiem = match.groups()
    if minute is None and meridiem is None:
        raise ValueError("A bare number is not a clock time")
    hour, minute, second = int(hour), int(minute or 0), Decimal(second or '0')
    if minute >= 60 or second >= 60 or (meridiem and not 1 <= hour <= 12) or (not meridiem and hour >= 24):
        raise ValueError("Clock time is outside the valid hour, minute or second range")
    if meridiem:
        hour = hour % 12 + (12 if meridiem.lower().startswith('p') else 0)
    return hour, minute, second


def is_clock_time(value):
    try:
        parse_clock_time(value)
        return True
    except ValueError:
        return False


def clock_style(value):
    text = str(value).strip()
    return ('12_hour' if re.search(r'[ap]\.?(?:m)\.?$', text, re.I) else '24_hour', text.count(':'))


def format_clock_time(value, output='24_hour'):
    if output not in ('24_hour', '12_hour'):
        raise ValueError("Choose 24_hour or 12_hour clock format")
    hour, minute, second = parse_clock_time(value)
    sec = format(second, 'f').rstrip('0').rstrip('.') if second % 1 else str(int(second))
    if second < 10:
        sec = '0' + sec
    suffix = '' if output == '24_hour' else (' AM' if hour < 12 else ' PM')
    shown_hour = hour if output == '24_hour' else hour % 12 or 12
    return f'{shown_hour:02d}:{minute:02d}:{sec}{suffix}'


def normalize_clock_times(series, settings):
    output = settings.get('format', '24_hour')
    if output not in ('24_hour', '12_hour'):
        raise ValueError("Choose 24_hour or 12_hour clock format")
    def convert(value):
        if missing(value):
            return value
        try:
            return format_clock_time(value, output)
        except ValueError:
            return value
    return series.map(convert)

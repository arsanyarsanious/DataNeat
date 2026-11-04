import re
from collections import Counter
from datetime import date, datetime

from .common import missing

MONTH_FORMATS = ["%b %d %Y", "%B %d, %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"]


def detect_date_pattern(value):
    s = str(value).strip()
    if isinstance(value, (datetime, date)) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[T ].+", s
    ):
        return "ISO datetime"
    if "T" in s:
        head, _, tail = s.partition("T")
        if tail and re.fullmatch(r"\d{1,4}[-/]\d{1,2}[-/]\d{2,4}",head):
            pattern=detect_date_pattern(head)
            if pattern:return pattern+" datetime"
    match = re.fullmatch(r"(\d{1,4})([-/])(\d{1,2})\2(\d{2,4})", s)
    if match:
        a, sep, b, c = match.groups()
        if len(a) == 4:
            return f"YYYY{sep}MM{sep}DD"
        if len(c) == 4:
            if int(a) > 12:
                return f"DD{sep}MM{sep}YYYY"
            if int(b) > 12:
                return f"MM{sep}DD{sep}YYYY"
            return f"DD{sep}MM{sep}YYYY_or_MM{sep}DD{sep}YYYY"
    if (
        re.search(
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b",
            s,
            re.IGNORECASE,
        )
        and re.search(r"\b\d{1,2}\b", s)
        and re.search(r"\b\d{4}\b", s)
    ):
        return "Month-name formats"
    return None


def parse_date(value, interpretation=None):
    if isinstance(value, (datetime, date)):
        return value
    s = str(value).strip()
    pattern = detect_date_pattern(s)
    if pattern == "ISO datetime":
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    if pattern and pattern.endswith(" datetime"):
        head, _, tail=s.partition("T")
        parsed=parse_date(head,interpretation)
        return datetime.fromisoformat(parsed.date().isoformat()+"T"+tail)
    if pattern == "Month-name formats":
        for fmt in MONTH_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass
        raise ValueError("Invalid month-name date")
    if not pattern:
        raise ValueError("Not a supported date")
    pieces = re.split(r"[-/]", s)
    if len(pieces[0]) == 4:
        y, m, d = map(int, pieces)
    else:
        a, b, y = map(int, pieces)
        if "_or_" in pattern:
            if a == b:
                interpretation = "day_first"
            if interpretation not in ("day_first", "month_first"):
                raise ValueError("Ambiguous date requires interpretation")
            d, m = (a, b) if interpretation == "day_first" else (b, a)
        else:
            d, m = (a, b) if pattern.startswith("DD") else (b, a)
    return datetime(y, m, d)


def is_ambiguous_numeric_date(value):
    if isinstance(value,str) and "T" in value:
        return is_ambiguous_numeric_date(value.partition("T")[0])
    pattern = detect_date_pattern(value)
    if not pattern or "_or_" not in pattern:
        return False
    try:
        return parse_date(value, "day_first") != parse_date(value, "month_first")
    except ValueError:
        return False


def infer_numeric_date_format(value):
    pattern = detect_date_pattern(value)
    if pattern and ("_or_" not in pattern):
        try:
            parse_date(value)
            return pattern
        except ValueError:
            pass
    return None


def is_valid_date(value):
    try:
        parse_date(value, "day_first")
        return True
    except (ValueError, TypeError, OverflowError):
        return False


def is_invalid_calendar_date(value):
    return bool(detect_date_pattern(value)) and not is_valid_date(value)


def analyze_date_column(series):
    values = [v for v in series if not missing(v)]
    patterns = Counter(detect_date_pattern(v) or "unrecognized" for v in values)
    ambiguous = [str(v) for v in values if is_ambiguous_numeric_date(v)]
    invalid = [str(v) for v in values if is_invalid_calendar_date(v)]
    dd = sum(
        bool((p := infer_numeric_date_format(v)) and p.startswith("DD")) for v in values
    )
    mm = sum(
        bool((p := infer_numeric_date_format(v)) and p.startswith("MM")) for v in values
    )
    return {
        "patterns": dict(patterns),
        "ambiguous_count": len(ambiguous),
        "ambiguous_examples": ambiguous[:5],
        "invalid_count": len(invalid),
        "invalid_examples": invalid[:5],
        "dd_mm_evidence": dd,
        "mm_dd_evidence": mm,
        "conflicting_evidence": bool(dd and mm),
        "suggested_interpretation": "day_first"
        if dd and not mm
        else "month_first"
        if mm and not dd
        else None,
    }


DATE_OUTPUT_FORMATS = {
    "YYYY-MM-DD":"%Y-%m-%d", "DD/MM/YYYY":"%d/%m/%Y",
    "MM/DD/YYYY":"%m/%d/%Y", "YYYY/MM/DD":"%Y/%m/%d",
    "DD-MM-YYYY":"%d-%m-%Y", "MM-DD-YYYY":"%m-%d-%Y",
}

def parse_formatted_date(value, interpretation=None, source_format=None):
    if source_format and isinstance(value, str):
        pattern=DATE_OUTPUT_FORMATS[source_format]
        head, separator, tail=value.partition("T")
        parsed=datetime.strptime(head,pattern)
        return datetime.fromisoformat(parsed.date().isoformat()+"T"+tail) if separator else parsed
    return parse_date(value, interpretation)

def render_date(parsed, output_format="YYYY-MM-DD", include_time=False):
    if output_format == "YYYY-MM-DD":
        return parsed.isoformat() if include_time else parsed.date().isoformat() if hasattr(parsed,"date") else parsed.isoformat()
    text=parsed.strftime(DATE_OUTPUT_FORMATS[output_format])
    return text+"T"+parsed.timetz().isoformat() if include_time and isinstance(parsed,datetime) else text

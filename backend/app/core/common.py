import re
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation

import pandas as pd

DEFAULT_MARKERS = {"", "null", "none", "n/a", "na", "nan", "-", "empty", "blank", "nil", "undefined", "missing", "not available", "not applicable", "n.a.", "n.a", "#n/a", "<null>", "(null)"}
ACTIVE_MARKERS = ContextVar("active_markers", default=None)
ACTIVE_SETTINGS = ContextVar("active_settings", default={})


def marker_set(markers):
    return None if markers is None else frozenset(str(m).lower() for m in markers)


def missing(value, markers=None):
    if markers is None:
        markers = ACTIVE_MARKERS.get()
    return bool(pd.isna(value)) or (
        isinstance(value, str)
        and value.strip().lower()
        in (DEFAULT_MARKERS if markers is None else markers if isinstance(markers, frozenset) else {str(m).lower() for m in markers})
    )


def scalar(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def numeric(value):
    text = str(value).strip()
    text = re.sub(r"^[\$€£]", "", text).strip()
    if text.endswith("%"):
        text = text[:-1]
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?", text):
        raise ValueError("Unsupported numeric formatting")
    try:
        result = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("Unsupported numeric exponent") from exc
    if not result.is_finite():
        raise ValueError("Nonfinite number")
    return result

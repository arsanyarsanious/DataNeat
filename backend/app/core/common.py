import re
from decimal import Decimal

import pandas as pd

DEFAULT_MARKERS = {"", "null", "none", "n/a", "na", "nan", "-"}


def missing(value, markers=None):
    return bool(pd.isna(value)) or (
        isinstance(value, str)
        and value.strip().lower()
        in (DEFAULT_MARKERS if markers is None else {str(m).lower() for m in markers})
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
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", text):
        raise ValueError("Unsupported numeric formatting")
    result = Decimal(text.replace(",", ""))
    if not result.is_finite():
        raise ValueError("Nonfinite number")
    return result

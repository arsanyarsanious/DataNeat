import re

from .common import missing, numeric
from .currency import normalize_currency, parse_currency
from .date_analyzer import is_valid_date, parse_date
from .imputation import impute_missing_values
from .percentage import normalize_percentage
from .phone import normalize_phone
from .symbols import normalize_symbols
from .type_detector import BOOLEAN_MAP


def normalize_missing_values(series, markers):
    return series.map(lambda v: None if missing(v, markers) else v)


def trim_whitespace(series):
    return series.map(
        lambda v: re.sub(r"\s+", " ", v.strip()) if isinstance(v, str) else v
    )


def normalize_capitalization(series, strategy):
    if strategy not in ("lower", "upper", "title"):
        raise ValueError("Unknown capitalization strategy")
    return series.map(
        lambda v: getattr(v, strategy)() if isinstance(v, str) and not missing(v) else v
    )


def normalize_numeric(series, settings):

    def convert(v):
        if missing(v):
            return v
        try:
            text = str(v).strip()
            try:
                number, marker = parse_currency(v)
            except ValueError:
                number, marker = numeric(v), None
            # Preserve currency identity. Different currencies are never merged.
            prefix = marker or (text[0] if text and text[0] in "$€£" else "")
            result = format(number, "f")
            if "." in result:
                result = result.rstrip("0").rstrip(".")
            if text.endswith("%"):
                result += "%"
            if prefix:
                result = prefix + (" " if prefix.isalpha() else "") + result
            return result
        except ValueError:
            return v

    return series.map(convert)


def normalize_boolean(series, mapping=None):
    mapping = mapping or BOOLEAN_MAP
    return series.map(
        lambda v: mapping.get(str(v).strip().lower(), v) if not missing(v) else v
    )


def normalize_dates(series, settings):
    def convert(v):
        if missing(v):
            return v
        try:
            parsed = parse_date(v, settings.get("interpretation"))
            return (
                parsed.isoformat()
                if settings.get("include_time")
                else parsed.date().isoformat()
                if hasattr(parsed, "date")
                else parsed.isoformat()
            )
        except (ValueError, TypeError, OverflowError):
            return v

    return series.map(convert)


def resolve_invalid_dates(series, settings):
    result = series.copy(deep=True)
    action = settings.get("action", "manual")
    if action == "empty":
        return result.map(
            lambda value: (
                None if not missing(value) and not is_valid_date(value) else value
            )
        )
    if action != "manual":
        raise ValueError("Choose empty or manual date correction")
    for key, replacement in settings.get("replacements", {}).items():
        try:
            row = int(key)
        except (ValueError, TypeError):
            raise ValueError("Invalid row reference")
        if row not in result.index:
            raise ValueError("The selected row no longer exists")
        if missing(result.loc[row]) or is_valid_date(result.loc[row]):
            raise ValueError("Manual correction only applies to invalid dates")
        if replacement is not None:
            if (
                not isinstance(replacement, str)
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", replacement)
                or not is_valid_date(replacement)
            ):
                raise ValueError(
                    "Manual replacements must be valid YYYY-MM-DD dates or empty cells"
                )
        result.loc[row] = replacement
    return result


def remove_duplicates(df, subset=None):
    return df.drop_duplicates(subset=subset).copy()


def validate_imputation_approval(approved_plan):
    for op in approved_plan:
        if (
            op.get("enabled")
            and op["operation"] == "impute_missing_values"
            and op.get("parameters", {}).get("method", "preserve") != "preserve"
            and op.get("parameters", {}).get("confirmed") is not True
        ):
            raise ValueError(
                f"Confirm imputation estimates for {op.get('column')} after reviewing the preview"
            )


def apply_cleaning_plan(df, approved_plan, require_approval=True):
    if require_approval:
        validate_imputation_approval(approved_plan)
    # Dependencies are run before imputation regardless of the submitted UI order.
    priorities = {
        "normalize_missing_values": 0,
        "trim_whitespace": 1,
        "normalize_numeric": 2,
        "normalize_boolean": 2,
        "normalize_dates": 2,
        "resolve_invalid_dates": 2,
        "impute_missing_values": 4,
        "remove_duplicates": 5,
        "rename_column": 6,
    }
    has_imputation = any(
        op.get("enabled")
        and op["operation"] == "impute_missing_values"
        and op.get("parameters", {}).get("method", "preserve") != "preserve"
        for op in approved_plan
    )
    ordered = (
        sorted(approved_plan, key=lambda op: priorities.get(op["operation"], 3))
        if has_imputation
        else approved_plan
    )
    result = df.copy(deep=True)
    logs = []
    for op in ordered:
        if not op.get("enabled", False):
            continue
        column, operation, settings = (
            op.get("column"),
            op["operation"],
            op.get("parameters", {}),
        )
        rows_before = len(result)
        audit = {}
        if operation == "impute_missing_values":
            try:
                result, audit = impute_missing_values(
                    result, column, settings.get("method", "preserve"), settings
                )
            except ValueError as exc:
                raise ValueError(f"Imputation for {column}: {exc}") from exc
            modified = audit["imputed_count"]
        elif operation == "remove_duplicates":
            result = remove_duplicates(result, settings.get("subset"))
            modified = 0
        elif operation == "rename_column":
            target = settings.get("name", "").strip()
            if column not in result or not target or target in result.columns:
                raise ValueError("Invalid or duplicate column name")
            result = result.rename(columns={column: target})
            modified = 0
        else:
            if column not in result:
                raise ValueError("Unknown column")
            series = result[column]
            functions = {
                "trim_whitespace": lambda: trim_whitespace(series),
                "normalize_missing_values": lambda: normalize_missing_values(
                    series, settings.get("markers", [])
                ),
                "normalize_capitalization": lambda: normalize_capitalization(
                    series, settings.get("strategy", "title")
                ),
                "normalize_numeric": lambda: normalize_numeric(series, settings),
                "normalize_boolean": lambda: normalize_boolean(series),
                "normalize_dates": lambda: normalize_dates(series, settings),
                "resolve_invalid_dates": lambda: resolve_invalid_dates(
                    series, settings
                ),
                "normalize_currency": lambda: normalize_currency(series, settings),
                "normalize_percentage": lambda: normalize_percentage(series, settings),
                "normalize_symbols": lambda: normalize_symbols(series, settings),
                "normalize_phone": lambda: normalize_phone(series, settings),
            }
            if operation not in functions:
                raise ValueError("Unknown operation")
            changed = functions[operation]()
            modified = sum(
                (str(a), type(a).__name__) != (str(b), type(b).__name__)
                for a, b in zip(series, changed)
            )
            result[column] = changed
        logs.append(
            {
                "id": op.get("id"),
                "operation": operation,
                "column": column,
                "modified_values": modified,
                "status": "applied",
                "removed_rows": rows_before - len(result),
                "parameters": settings,
                **audit,
            }
        )
    return result, logs

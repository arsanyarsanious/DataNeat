import re

from .data_formats import FORMAT_ACTIONS, normalize_format, expand_structured
from .clock_time import normalize_clock_times
from .negative_values import absolute_values
from .duration import normalize_durations
from .common import missing, numeric
from .currency import normalize_currency, parse_currency
from .date_analyzer import is_valid_date, parse_date, parse_formatted_date, render_date
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


def normalize_boolean(series, mapping=None, output="true_false"):
    mapping = mapping or BOOLEAN_MAP
    def convert(value):
        if missing(value): return value
        normalized = mapping.get(str(value).strip().lower(), value)
        if output == "yes_no" and isinstance(normalized, bool): return "Yes" if normalized else "No"
        if output == "one_zero" and isinstance(normalized, bool): return "1" if normalized else "0"
        return normalized
    return series.map(convert)


def normalize_dates(series, settings):
    known=settings.get("_source_formats", {})
    def convert(index, value):
        if missing(value): return value
        try:
            parsed=parse_formatted_date(value, settings.get("interpretation"), known.get(int(index)))
            return render_date(parsed,settings.get("output_format","YYYY-MM-DD"),settings.get("include_time",False))
        except (ValueError, TypeError, OverflowError):
            return value
    return series.__class__([convert(index,value) for index,value in series.items()],index=series.index,name=series.name,dtype=object)


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


def apply_cleaning_plan(df, approved_plan, require_approval=True, progress=None):
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
        if progress:
            progress(op)
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
        elif operation == "expand_structured":
            previous_columns=set(result.columns)
            result=expand_structured(result,column,settings)
            modified=sum(not missing(value) for name in result.columns if name not in previous_columns for value in result[name])
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
                "normalize_boolean": lambda: normalize_boolean(series, output=settings.get("format", "true_false")),
                "normalize_time": lambda: normalize_clock_times(series, settings),
                "absolute_values": lambda: absolute_values(series),
                "normalize_duration": lambda: normalize_durations(series),
                "normalize_dates": lambda: normalize_dates(series, settings),
                "resolve_invalid_dates": lambda: resolve_invalid_dates(
                    series, settings
                ),
                "normalize_currency": lambda: normalize_currency(series, settings),
                "normalize_percentage": lambda: normalize_percentage(series, settings),
                "normalize_symbols": lambda: normalize_symbols(series, settings),
                "normalize_phone": lambda: normalize_phone(series, settings),
            }
            functions.update({name: (lambda name=name: normalize_format(series,name,settings)) for name in FORMAT_ACTIONS})
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

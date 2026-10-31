import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..core.data_formats import FORMAT_ACTIONS, validate_format_settings
from ..core.currency import CURRENCY_CODES
from ..core.date_analyzer import is_valid_date
from ..core.imputation import validate_parameters
from ..core.phone import REGIONS


class Operation(BaseModel):
    id: str = ""
    column: str | None = None
    operation: Literal[
        "trim_whitespace",
        "normalize_missing_values",
        "normalize_capitalization",
        "normalize_numeric",
        "normalize_boolean",
        "normalize_dates",
        "normalize_duration",
        "normalize_time",
        "absolute_values",
        "normalize_number_format", "convert_units", "convert_numeric_dates", "convert_timezone",
        "normalize_structured", "expand_structured", "normalize_coordinates", "normalize_url", "normalize_ip",
        "resolve_invalid_dates",
        "normalize_currency",
        "normalize_percentage",
        "normalize_phone",
        "normalize_symbols",
        "remove_duplicates",
        "rename_column",
        "impute_missing_values",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False

    @model_validator(mode="after")
    def validate_settings(self):
        if self.operation != "remove_duplicates" and not self.column:
            raise ValueError("This operation requires a column")
        settings = self.parameters
        if self.operation in FORMAT_ACTIONS | {"expand_structured"}: validate_format_settings(self.operation,settings)
        if self.operation == "impute_missing_values" and self.enabled:
            validate_parameters(settings.get("method", "preserve"), settings)
        if self.operation == "normalize_boolean" and settings.get("format", "true_false") not in ("true_false", "yes_no", "one_zero"):
            raise ValueError("Choose true/false, Yes/No, or 1/0 boolean labels")
        if self.operation == "normalize_capitalization" and settings.get(
            "strategy", "title"
        ) not in ("lower", "upper", "title"):
            raise ValueError("Choose lower, upper, or title capitalization")
        if self.operation == "normalize_time" and settings.get("format", "24_hour") not in ("24_hour", "12_hour"):
            raise ValueError("Choose 24_hour or 12_hour clock format")
        if self.operation == "normalize_dates":
            from ..core.date_analyzer import DATE_OUTPUT_FORMATS
            if not isinstance(settings.get("output_format", "YYYY-MM-DD"), str) or settings.get("output_format", "YYYY-MM-DD") not in DATE_OUTPUT_FORMATS:
                raise ValueError("Choose a supported date output format")
            if settings.get("interpretation", "preserve") not in (
                "preserve",
                "day_first",
                "month_first",
            ):
                raise ValueError(
                    "Choose preserve, day_first, or month_first date interpretation"
                )
            if not isinstance(settings.get("include_time", False), bool):
                raise ValueError("include_time must be a boolean")
        if self.operation == "normalize_missing_values":
            markers = settings.get("markers", [])
            if (
                not isinstance(markers, list)
                or len(markers) > 100
                or any(not isinstance(v, str) or len(v) > 100 for v in markers)
            ):
                raise ValueError("markers must be a list of at most 100 short strings")
        if self.operation == "remove_duplicates":
            subset = settings.get("subset")
            if subset is not None and (
                not isinstance(subset, list)
                or not subset
                or len(subset) > 200
                or any(not isinstance(v, str) for v in subset)
            ):
                raise ValueError(
                    "subset must be null or a nonempty list of column names"
                )
        if self.operation == "resolve_invalid_dates":
            if settings.get("action", "manual") not in ("manual", "empty"):
                raise ValueError("Choose manual or empty for invalid dates")
            replacements = settings.get("replacements", {})
            if not isinstance(replacements, dict) or len(replacements) > 100000:
                raise ValueError("Invalid row replacements")
            for row, value in replacements.items():
                if not isinstance(row, str) or not row.isdigit():
                    raise ValueError("Invalid row reference")
                if value is not None and (
                    not isinstance(value, str)
                    or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
                    or not is_valid_date(value)
                ):
                    raise ValueError(
                        "Enter a valid YYYY-MM-DD date or choose an empty cell"
                    )
        if self.operation in (
            "normalize_percentage",
            "normalize_currency",
            "normalize_symbols",
        ):
            if settings.get(
                "action",
                "legacy" if self.operation != "normalize_symbols" else "preserve",
            ) not in (
                ("preserve", "add", "remove")
                if self.operation == "normalize_symbols"
                else ("preserve", "add", "remove", "legacy")
            ):
                raise ValueError("Choose add to all, remove from all, or no change")
        if (
            self.operation in ("normalize_currency", "normalize_symbols")
            and settings.get("action") == "add"
            and self.enabled
        ):
            symbol = settings.get("symbol", "")
            if (
                not isinstance(symbol, str)
                or not symbol.strip()
                or len(symbol.strip()) > 12
                or re.search(r"[\d\s\x00-\x1f]", symbol.strip())
            ):
                raise ValueError("Enter a short symbol without digits or spaces")
        if self.operation in (
            "normalize_currency",
            "normalize_symbols",
        ) and settings.get("position", "prefix") not in ("prefix", "suffix"):
            raise ValueError("Choose prefix or suffix")
        if self.operation == "normalize_phone":
            if settings.get("action", "preserve") not in (
                "preserve",
                "international",
                "international_digits",
                "national",
                "remove_plus",
                "add_plus",
            ):
                raise ValueError("Choose a supported phone format")
            region = settings.get("region", "")
            if (
                settings.get("action", "preserve") not in ("preserve", "remove_plus")
                and region
                and region not in REGIONS
            ):
                raise ValueError("Choose a supported phone country")
            if (
                self.enabled
                and settings.get("action") in ("international", "international_digits")
                and not region
            ):
                raise ValueError("Choose the country used for local phone numbers")
        if self.operation == "normalize_percentage":
            if settings.get("format", "with_sign") not in (
                "with_sign",
                "without_sign",
                "ratio",
            ):
                raise ValueError(
                    "Choose percentage sign, percentage points, or fractional ratio output"
                )
            if settings.get("bare_interpretation", "preserve") not in (
                "preserve",
                "percentage_points",
                "fraction",
            ):
                raise ValueError(
                    "Confirm how bare percentage numbers should be interpreted"
                )
        if (
            self.operation == "normalize_currency"
            and self.enabled
            and settings.get("action", "legacy") == "legacy"
        ):
            if settings.get("currency") not in CURRENCY_CODES:
                raise ValueError("Choose the intended currency")
            if settings.get("format", "code") not in ("code", "symbol", "number"):
                raise ValueError("Choose code, symbol, or number output")
            if settings.get("format") == "symbol" and settings["currency"] not in (
                "USD",
                "EUR",
                "GBP",
            ):
                raise ValueError("Symbol output supports USD, EUR, and GBP")
            if not isinstance(settings.get("assume_unlabelled", False), bool):
                raise ValueError("Confirm unlabelled amounts explicitly")
            aliases = settings.get("symbol_aliases", [])
            if not isinstance(aliases, list) or any(
                v not in ("$", "¥") for v in aliases
            ):
                raise ValueError("Only ambiguous symbols may be explicitly assigned")
            if "$" in aliases and settings["currency"] not in (
                "USD",
                "CAD",
                "AUD",
                "NZD",
                "SGD",
                "HKD",
            ):
                raise ValueError(
                    "$ can only be assigned to a supported dollar currency"
                )
            if "¥" in aliases and settings["currency"] not in ("JPY", "CNY"):
                raise ValueError("¥ can only be assigned to JPY or CNY")
        if self.operation == "rename_column":
            name = settings.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 512:
                raise ValueError(
                    "Provide a nonempty column name of at most 512 characters"
                )
        return self


class CleaningRequest(BaseModel):
    operations: list[Operation] = Field(max_length=1000)


class EditorRequest(BaseModel):
    revision: int = Field(ge=0)
    column: str = Field(min_length=1, max_length=512)
    row_index: int = Field(ge=0)
    scope: Literal["cell", "column", "matching", "invalid_dates", "issue", "issue_columns", "values"] = "cell"
    action: Literal[
        "replace",
        "trim_whitespace",
        "normalize_dates",
        "normalize_duration",
        "normalize_time",
        "absolute_values",
        "normalize_number_format", "convert_units", "convert_numeric_dates", "convert_timezone",
        "normalize_structured", "expand_structured", "normalize_coordinates", "normalize_url", "normalize_ip",
        "normalize_boolean",
        "normalize_numeric",
        "normalize_capitalization",
        "normalize_currency",
        "normalize_percentage",
        "normalize_symbols",
        "normalize_phone",
        "impute_missing_values",
        "remove_duplicates",
        "resolve_invalid_dates",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    value: str | float | bool | None = None
    confirmed: bool = False

    @model_validator(mode="after")
    def validate_action(self):
        if self.scope in ("matching", "invalid_dates", "issue", "issue_columns", "values") and self.action != "replace":
            raise ValueError("Matching-value scope is available for manual replacements only")
        if self.scope == "issue_columns":
            columns = self.parameters.get("columns")
            kind = self.parameters.get("issue_kind")
            if not isinstance(columns, list) or not 1 <= len(columns) <= 200 or any(not isinstance(name, str) or not name for name in columns) or len(set(columns)) != len(columns) or self.column not in columns:
                raise ValueError("Select the affected columns, including the current column")
            if not isinstance(kind, str) or not re.fullmatch(r"[a-z_]{1,80}", kind):
                raise ValueError("Select one issue type")
        if self.action != "replace":
            Operation(
                column=self.column,
                operation=self.action,
                parameters={**self.parameters, "confirmed": True},
                enabled=True,
            )
        if isinstance(self.value, str) and len(self.value) > 10000:
            raise ValueError("Replacement value is too long")
        if self.scope == "values":
            sources = self.parameters.get("source_values")
            if not isinstance(sources, list) or not 2 <= len(sources) <= 1000 or any(not isinstance(v, str) or not v.strip() or len(v) > 10000 for v in sources):
                raise ValueError("Select between 2 and 1000 nonempty text values")
            if len(set(sources)) != len(sources) or not isinstance(self.value, str) or not self.value.strip():
                raise ValueError("Select distinct source values and enter the final text")
        return self

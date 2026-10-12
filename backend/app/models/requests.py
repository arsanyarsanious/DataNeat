import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..core.currency import CURRENCY_CODES
from ..core.date_analyzer import is_valid_date
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
        "resolve_invalid_dates",
        "normalize_currency",
        "normalize_percentage",
        "normalize_phone",
        "normalize_symbols",
        "remove_duplicates",
        "rename_column",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False

    @model_validator(mode="after")
    def validate_settings(self):
        if self.operation != "remove_duplicates" and not self.column:
            raise ValueError("This operation requires a column")
        settings = self.parameters
        if self.operation == "normalize_capitalization" and settings.get(
            "strategy", "title"
        ) not in ("lower", "upper", "title"):
            raise ValueError("Choose lower, upper, or title capitalization")
        if self.operation == "normalize_dates":
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

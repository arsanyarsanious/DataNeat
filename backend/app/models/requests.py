from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
        if self.operation == "rename_column":
            name = settings.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 512:
                raise ValueError(
                    "Provide a nonempty column name of at most 512 characters"
                )
        return self


class CleaningRequest(BaseModel):
    operations: list[Operation] = Field(max_length=1000)

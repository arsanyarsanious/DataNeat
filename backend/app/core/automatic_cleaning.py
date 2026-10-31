"""Survey-authorized policies applied to the current copy, without a review stage."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .workflow import manual_acceptances

class ColumnException(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trim: bool | None = None
    boolean: Literal["preserve", "true_false", "yes_no", "one_zero"] | None = None
    capitalization: Literal["preserve", "title", "upper", "lower"] | None = None
    dates: Literal["preserve", "unambiguous", "day_first", "month_first"] | None = None
    date_output: Literal["YYYY-MM-DD","DD/MM/YYYY","MM/DD/YYYY","YYYY/MM/DD","DD-MM-YYYY","MM-DD-YYYY"] | None = None
    missing: Literal["preserve", "median", "mean"] | None = None

class AutomaticAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trim: bool = True
    boolean: Literal["preserve", "true_false", "yes_no", "one_zero"] = "preserve"
    capitalization: Literal["preserve", "title", "upper", "lower"] = "preserve"
    dates: Literal["preserve", "unambiguous", "day_first", "month_first"] = "preserve"
    date_output: Literal["YYYY-MM-DD","DD/MM/YYYY","MM/DD/YYYY","YYYY/MM/DD","DD-MM-YYYY","MM-DD-YYYY"] = "YYYY-MM-DD"
    missing: Literal["preserve", "median", "mean"] = "preserve"
    duplicates: Literal["preserve", "remove"] = "preserve"
    exceptions: dict[str, ColumnException] = Field(default_factory=dict, max_length=200)


def automatic_steps(record, answers):
    steps, skipped = [], []
    unknown = set(answers.exceptions) - set(map(str, record["editor_df"].columns))
    if unknown:
        raise ValueError("Exception columns are not in this sheet: " + ", ".join(sorted(unknown)))
    protected = {v["column"] for v in manual_acceptances(record)}
    if record["editor_df"].empty:
        return steps, ["The sheet has no rows."]
    def fix(column, action, parameters):
        steps.append({"kind":"fix", "body":{"revision":record["editor_revision"], "column":column, "row_index":int(record["editor_df"].index[0]), "scope":"column", "action":action, "parameters":parameters}})
    for col in record["editor_profile"]["columns"]:
        name, kind = col["column_name"], col["detected_type"]
        policy = answers.model_dump(exclude={"exceptions"})
        if name in answers.exceptions:
            policy.update(answers.exceptions[name].model_dump(exclude_none=True))
        if col.get("missing_marker_review", {}).get("count"):
            skipped.append(f"{name}: review possible missing-value labels before automatic cleaning.")
            continue
        if name in protected or kind == "identifier":
            skipped.append(f"{name}: preserved identifier or existing user-entered corrections.")
            continue
        if policy["trim"] and any(isinstance(value, str) and re.sub(r"\s+", " ", value.strip()) != value for value in record["editor_df"][name]):
            fix(name, "trim_whitespace", {})
        if kind == "boolean" and policy["boolean"] != "preserve":
            fix(name, "normalize_boolean", {"format":policy["boolean"]})
        if kind in ("text", "category", "categorical") and policy["capitalization"] != "preserve":
            fix(name, "normalize_capitalization", {"strategy":policy["capitalization"]})
        if kind in ("date", "datetime") and policy["dates"] != "preserve":
            fix(name, "normalize_dates", {"interpretation":"preserve" if policy["dates"] == "unambiguous" else policy["dates"], "include_time":kind == "datetime", "output_format":policy["date_output"]})
        # Restrict automatic estimates to ordinary numeric measurements; units and
        # currency/percentage scales require explicit column-level interpretation.
        if policy["missing"] != "preserve" and col.get("missing_count"):
            if kind in ("integer", "decimal", "numeric", "float") and col.get("match_score", 0) == 1:
                fix(name, "impute_missing_values", {"method":policy["missing"], "confirmed":True})
            else:
                skipped.append(f"{name}: missing values preserved; not a fully numeric measurement column.")
    if answers.duplicates == "remove":
        fix(str(record["editor_df"].columns[0]), "remove_duplicates", {})
    return steps, skipped

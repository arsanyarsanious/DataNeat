"""Versioned, locally replayable decisions. Never infer approval from a suggestion."""
import copy
import fnmatch
import re
import uuid
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .common import DEFAULT_MARKERS, ACTIVE_MARKERS, ACTIVE_SETTINGS, missing, scalar, numeric, marker_set
from .currency import parse_currency
from .percentage import parse_percentage
from .negative_values import is_negative
from .date_analyzer import is_valid_date, is_ambiguous_numeric_date, parse_formatted_date
from .type_detector import is_boolean
from .profiler import profile_dataframe
from .interactive import propose, annotate
from .imputation_readiness import (ANALYSIS_SCHEMA_VERSION, IMPUTATION_READINESS_POLICY,
                                   actual_empty, ensure_imputation_ready, readiness_from_annotations)
from ..models.requests import EditorRequest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreparationColumn(StrictModel):
    excluded: bool = False
    trim: bool | None = None
    collapse: bool | None = None
    markers: list[str] | None = Field(default=None, max_length=100)


class Preparation(StrictModel):
    trim: bool = True
    collapse: bool = False
    normalize_missing: bool = True
    markers: list[str] = Field(default_factory=lambda: sorted(DEFAULT_MARKERS), max_length=100)
    columns: dict[str, PreparationColumn] = Field(default_factory=dict, max_length=200)


class ColumnRule(StrictModel):
    allow_negative: bool = True
    type: Literal["", "text", "identifier", "numeric", "salary", "location", "category", "currency", "percentage", "boolean", "date", "datetime", "time", "duration", "phone", "email", "coordinate", "url", "ip"] = ""
    required: bool = False
    unique: bool = False
    allowed: list[str] = Field(default_factory=list, max_length=1000)
    minimum: str = Field(default="", max_length=100)
    maximum: str = Field(default="", max_length=100)
    date_min: str = ""
    date_max: str = ""
    pattern: str = Field(default="", max_length=200)
    currency: str = Field(default="", max_length=10)
    percentage_scale: Literal["", "points", "ratio"] = ""
    date_order: Literal["preserve", "dayfirst", "monthfirst"] = "preserve"
    severity: Literal["error", "warning"] = "error"

    @model_validator(mode="after")
    def bounds(self):
        try:
            values = [Decimal(v) for v in (self.minimum, self.maximum) if v]
            if any(not v.is_finite() for v in values):
                raise ValueError("Bounds must be finite numbers")
            if self.minimum and self.maximum and Decimal(self.minimum) > Decimal(self.maximum):
                raise ValueError("Minimum must not exceed maximum")
            for value in (self.date_min, self.date_max):
                if value:
                    date.fromisoformat(value)
            if self.date_min and self.date_max and self.date_min > self.date_max:
                raise ValueError("Date minimum must not exceed date maximum")
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid rule bounds: {exc}") from exc
        return self


class MissingMarkerChoice(StrictModel):
    convert: bool


class NegativePolicy(StrictModel):
    allow_negative: bool

class Decision(StrictModel):
    kind: Literal["preparation", "rules", "ignore", "fix", "rename", "missing_markers", "negative_policy", "quality"]
    settings: dict = Field(default_factory=dict)
    body: dict = Field(default_factory=dict)
    column: str = ""
    issue: str = ""
    row_index: int | None = Field(default=None, ge=0)
    value: str | None = None
    reason: str = Field(default="Reviewed and accepted", max_length=500)

    @model_validator(mode="after")
    def valid(self):
        if self.kind == "quality":
            from .quality_tools import validate_settings
            self.settings = validate_settings(self.settings)
        elif self.kind == "negative_policy":
            self.settings = NegativePolicy(**self.settings).model_dump()
            if not self.column: raise ValueError("Select a column")
        elif self.kind == "missing_markers":
            self.settings = MissingMarkerChoice(**self.settings).model_dump()
            if not self.column: raise ValueError("Select a column")
        elif self.kind == "preparation":
            self.settings = Preparation(**self.settings).model_dump()
        elif self.kind == "rules":
            self.settings = ColumnRule(**self.settings).model_dump()
            if not self.column:
                raise ValueError("Select a column")
        elif self.kind == "rename":
            from ..models.requests import Operation
            Operation(column=self.column, operation="rename_column", parameters=self.settings)
            self.settings["name"] = self.settings["name"].strip()
        elif self.kind == "fix":
            self.body = EditorRequest(**self.body).model_dump()
        elif not self.column or not self.issue:
            raise ValueError("Select a column and issue to ignore")
        return self


class Recipe(StrictModel):
    version: Literal[1] = 1
    name: str = Field(default="My cleaning recipe", min_length=1, max_length=120)
    steps: list[Decision] = Field(default_factory=list, max_length=200)
    source_columns: list[str] = Field(default_factory=list, max_length=200)


def settings_for(record):
    result = copy.deepcopy(record.get("column_rules", {}))
    prep = record.get("preparation_settings")
    if prep:
        for column in record["editor_df"].columns:
            local = prep.get("columns", {}).get(column, {})
            markers = local.get("markers")
            result.setdefault(column, {})["markers"] = [""] if local.get("excluded") or not prep.get("normalize_missing") else prep["markers"] if markers is None else markers
    if record.get("missing_marker_review_version"):
        for column in record["editor_df"].columns:
            policy = record.get("missing_marker_policies", {}).get(column)
            config = result.setdefault(column, {})
            config["markers"] = sorted(DEFAULT_MARKERS) if policy and policy.get("convert") else [""]
            config["marker_review"] = policy is None
    return result


def declared_date(value, settings):
    if is_ambiguous_numeric_date(value) and settings.get("date_order", "preserve") == "preserve":
        raise ValueError("Ambiguous date requires a declared interpretation")
    from dateutil.parser import parse
    if not is_valid_date(value):
        raise ValueError("Invalid date")
    return value.date() if isinstance(value, datetime) else value if isinstance(value, date) else parse(str(value), dayfirst=settings.get("date_order") == "dayfirst").date()


def number_for(value, rule):
    if rule.get("type") == "percentage":
        amount, marked = parse_percentage(value)
        if not marked and not rule.get("percentage_scale"):
            raise ValueError("Declare bare percentage scale")
        return amount * 100 if not marked and rule.get("percentage_scale") == "ratio" else amount
    if rule.get("type") == "currency":
        amount, marker = parse_currency(value)
        if marker and rule.get("currency") and marker.casefold() != rule["currency"].casefold():
            raise ValueError("Currency label differs from the declared literal label")
        return amount
    return numeric(value)


def matches_intent(value, rule):
    kind = rule.get("type", "")
    try:
        if kind in ("text", "identifier", "category", "location"):
            return isinstance(value, str)
        if kind == "percentage":
            parse_percentage(value)
        elif kind in ("numeric", "salary", "currency"):
            number_for(value, rule)
        elif kind == "boolean":
            return is_boolean(value)
        elif kind in ("date", "datetime"):
            declared_date(value, rule)
        elif kind == "time":
            from .clock_time import is_clock_time
            return is_clock_time(value)
        elif kind == "duration":
            from .duration import is_duration
            return is_duration(value)
        elif kind == "phone":
            from .phone import phone_text
            phone_text(value)
        elif kind == "email":
            return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", str(value)))
        elif kind in ("url", "ip"):
            from .data_formats import normalize_url, normalize_ip
            (normalize_url if kind == "url" else normalize_ip)(value, {"add_https": True})
        elif kind == "coordinate":
            from .data_formats import coordinate
            # An unlabeled coordinate may be either axis; axis-specific bounds
            # are checked by the coordinate cleaning tool.
            for axis in ("latitude", "longitude", "lat_lon", "lon_lat"):
                try:
                    coordinate(value, {"axis": axis})
                    return True
                except (ValueError, TypeError):
                    continue
            return False
        return True
    except (ValueError, TypeError, OverflowError):
        return False


def prepare(df, settings, check=lambda: None):
    config = Preparation(**settings).model_dump()
    unknown = set(config["columns"]) - set(df.columns)
    if unknown:
        raise ValueError("Unknown preparation columns: " + ", ".join(sorted(unknown)))
    result = df.copy(deep=True).astype(object)
    for column in df:
        check()
        local = config["columns"].get(column, {})
        if local.get("excluded"):
            continue
        markers = marker_set(config["markers"] if local.get("markers") is None else local["markers"])
        trim = config["trim"] if local.get("trim") is None else local["trim"]
        collapse = config["collapse"] if local.get("collapse") is None else local["collapse"]
        def convert(value):
            if config["normalize_missing"] and missing(value, markers):
                return None
            if isinstance(value, str):
                if trim:
                    value = value.strip()
                if collapse:
                    value = re.sub(r"\s+", " ", value)
            return value
        result[column] = result[column].map(convert)
    return result


def diff(before, after, action, revision, step_id, check=lambda: None):
    changes = []
    for column in before:
        check()
        if before.index.equals(after.index) and before[column].equals(after[column]) and list(map(type, before[column])) == list(map(type, after[column])):
            continue
        resulting_values = after[column].to_dict()
        for index, old in before[column].items():
            removed = index not in resulting_values
            new = None if removed else resulting_values[index]
            if removed or (type(old).__name__, str(old)) != (type(new).__name__, str(new)):
                changes.append({"step_id": step_id, "revision": revision, "action": action, "column": column, "row_index": int(index), "spreadsheet_row": int(index) + 2, "before": scalar(old), "after": scalar(new), "removed_row": removed})
    for column in after.columns.difference(before.columns):
        for index,value in after[column].items():
            if not missing(value): changes.append({"step_id":step_id,"revision":revision,"action":action,"column":column,"row_index":int(index),"spreadsheet_row":int(index)+2,"before":None,"after":scalar(value),"removed_row":False})
    return changes


def manual_acceptances(record):
    """Accept explicit user values only in the cells they actually changed.

    Deriving this from the surviving audit keeps prior edits, undo and rename
    consistent without changing the original values or disabling column checks.
    """
    by_step = {}
    for change in record.get("complete_changes", []):
        by_step.setdefault(change["step_id"], []).append(change)
    accepted = {}
    for step in record.get("editor_changes", []):
        action = step.get("action")
        if action == "rename_column":
            old, new = step.get("column"), step.get("parameters", {}).get("name")
            accepted = {(new if column == old else column, row): value for (column, row), value in accepted.items()}
            continue
        if action == "merge_records":
            detail = step.get("quality", {})
            survivor = detail.get("retained_row")
            transferred = {(name, survivor): accepted[(name, source)] for name, source in detail.get("source_rows", {}).items() if (name, source) in accepted}
            accepted = {key: value for key, value in accepted.items() if key[1] not in (survivor, detail.get("removed_row"))}
            accepted.update(transferred)
            continue
        explicit = action in ("replace", "unify_text_values") or action == "impute_missing_values" and step.get("parameters", {}).get("method") == "constant"
        for change in by_step.get(step.get("id"), []):
            key = (change["column"], change["row_index"])
            accepted.pop(key, None)
            value = change.get("after")
            if explicit and not change.get("removed_row") and value is not None and str(value).strip():
                accepted[key] = str(value)
    return [{"column": column, "row_index": row, "value": value, "issue": "*", "reason": "User-entered value accepted by the user; not independently verified"} for (column, row), value in accepted.items()]


def acceptance_index(entries):
    indexed = {}
    for entry in entries or []:
        indexed.setdefault((entry["column"], entry.get("row_index")), []).append(entry)
    return indexed


def estimated_cells(record):
    """Track surviving estimates/placeholders through formatting, rename and undo."""
    by_step={}
    for change in record.get("complete_changes",[]): by_step.setdefault(change["step_id"],[]).append(change)
    estimates=set()
    for step in record.get("editor_changes",[]):
        action=step.get("action")
        if action=="rename_column":
            old,new=step.get("column"),step.get("parameters",{}).get("name")
            estimates={(new if column==old else column,row) for column,row in estimates}
            continue
        changes=by_step.get(step.get("id"),[])
        if action == "merge_records":
            quality = step.get("quality", {})
            survivor = quality.get("retained_row")
            sources = quality.get("source_rows", {})
            transferred = {(name, survivor) for name, source in sources.items() if (name, source) in estimates}
            estimates = {(name, row) for name, row in estimates if row != survivor and row != quality.get("removed_row")}
            estimates.update(transferred)
        for change in changes:
            key=(change["column"],change["row_index"])
            if change.get("removed_row") or missing(change.get("after"), [""]) or action in ("replace","unify_text_values"): estimates.discard(key)
            if action=="impute_missing_values" and not change.get("removed_row") and not missing(change.get("after")):
                estimates.add(key)
    return estimates


def known_date_formats(record):
    known={}
    changes_by_step={}
    for change in record.get("complete_changes",[]):
        changes_by_step.setdefault(change["step_id"],[]).append(change)
    for entry in record.get("editor_changes",[]):
        column=entry.get("column")
        if entry.get("action")=="rename_column":
            target=entry["parameters"]["name"]
            known={((target if name==column else name),index):fmt for (name,index),fmt in known.items()}
        if entry.get("action") == "merge_records":
            detail = entry.get("quality", {})
            survivor = detail.get("retained_row")
            transferred = {(name, survivor): known[(name, source)] for name, source in detail.get("source_rows", {}).items() if (name, source) in known}
            known = {key: fmt for key, fmt in known.items() if key[1] not in (survivor, detail.get("removed_row"))}
            known.update(transferred)
            continue
        for change in changes_by_step.get(entry.get("id"),[]):
            known.pop((change["column"],change["row_index"]),None)
        if entry.get("action")=="normalize_dates":
            fmt=entry.get("parameters",{}).get("output_format","YYYY-MM-DD")
            for index in entry.get("date_format_rows",[]):known[(column,index)]=fmt
        if entry.get("action")=="impute_missing_values":
            estimate=entry.get("imputation",{})
            formats=estimate.get("date_output_formats",{})
            for change in changes_by_step.get(entry.get("id"),[]):
                fmt=formats.get(change["row_index"],formats.get(str(change["row_index"]))) or estimate.get("date_output_format")
                if fmt and not change.get("removed_row"): known[(column,change["row_index"])]=fmt
    return known


def workflow_annotations(df, report, part, columns=None, ignored=None):
    accepted_by_cell = acceptance_index(ignored)
    columns = list(df.columns) if columns is None else columns
    rows = annotate(df, report, part, columns)
    by_column = {c["column_name"]: c for c in report["columns"]}
    rule_rows = {c: [(finding, set(finding["row_indices"])) for finding in by_column[c].get("rule_findings", [])] for c in columns}
    for row, index in zip(rows, part.index):
        for cell, column in zip(row, columns):
            value = df.at[index, column]
            if by_column[column].get("intent", {}).get("marker_review") and isinstance(value, str) and value.strip() and value.strip().casefold() in DEFAULT_MARKERS:
                cell[:] = [{"kind":"missing_marker", "classification":"review", "message":"This text may represent a missing value. Convert missing-value labels in this column to empty cells, or keep them as text?"}]
            for finding, indices in rule_rows[column]:
                if int(index) in indices:
                    cell.append({"kind": finding["issue"], "message": finding["message"], "classification": "invalid" if finding["severity"] == "error" else "review"})
            for item in cell:
                item.setdefault("classification", "review" if item["kind"] in ("missing", "odd_value", "ambiguous_date", "duplicate") else "inconsistency" if item["kind"] in ("data_format", "time", "duration", "capitalization", "date_format", "currency", "percentage", "boolean", "whitespace", "symbol", "phone") else "invalid")
            accepted = [entry for entry in (*accepted_by_cell.get((column, None), []), *accepted_by_cell.get((column, int(index)), [])) if (entry.get("value") is None or entry["value"] == str(scalar(df.at[index, column])) or isinstance(df.at[index, column], bool) and entry["value"].casefold() == str(df.at[index, column]).casefold())]
            cell[:] = [item for item in cell if not any(entry["issue"] in ("*", item["kind"]) for entry in accepted)]
    return rows


def profile_record(record, check=lambda: None):
    # Invalidate old detection caches after adding new semantic types. Working
    # values, revision, user decisions and cleaning history remain unchanged.
    if record.get("analysis_schema_version") != ANALYSIS_SCHEMA_VERSION:
        for key in ("workflow_annotations", "workflow_raw_profile", "editor_issue_navigation"):
            record.pop(key, None)
        record.pop("_workflow_dirty", None)
    accepted_findings = [*record.get("ignored_findings", []), *manual_acceptances(record)]
    record["manual_acceptance_version"] = 2
    accepted_by_cell = acceptance_index(accepted_findings)
    settings = settings_for(record)
    date_formats = known_date_formats(record)
    changed = record.pop("_workflow_dirty", None)
    previous = record.get("workflow_raw_profile")
    if previous is None and record.get("workflow_annotations") and not record.get("ignored_findings"):
        previous = record.get("editor_profile")
    if not previous or not record.get("workflow_annotations"):
        changed = None
    token = ACTIVE_SETTINGS.set(settings)
    try:
        report = profile_dataframe(record["editor_df"], previous, changed)
    finally:
        ACTIVE_SETTINGS.reset(token)
    df = record["editor_df"]
    for column in report["columns"]:
        check()
        name = column["column_name"]
        if changed is not None and name not in changed:
            continue
        rule = settings.get(name, {})
        markers = marker_set(rule.get("markers"))
        if rule.get("allow_negative", True) and not any(rule.get(key) for key in ("type", "required", "unique", "allowed", "pattern", "minimum", "maximum", "date_min", "date_max")):
            column["rule_findings"] = []
            continue
        findings = {}
        duplicates = df[name].duplicated(keep=False)
        def add(kind, index, message, severity=None):
            item = findings.setdefault(kind, {"issue": kind, "column": name, "count": 0, "row_indices": [], "examples": [], "message": message, "severity": severity or rule.get("severity", "error")})
            item["row_indices"].append(int(index)); item["count"] += 1
            if len(item["examples"]) < 5:
                item["examples"].append(scalar(df.at[index, name]))
        for index, value in df[name].items():
            if missing(value, markers):
                if rule.get("required"):
                    add("rule_required", index, "A value is required by your column rule.")
                continue
            if rule.get("type") and not matches_intent(value, rule):
                add("rule_type", index, "Value conflicts with your declared type, currency label, or date interpretation.")
            if not rule.get("allow_negative", True) and is_negative(value):
                add("rule_negative", index, "Negative values are not allowed in this column. Remove the minus sign only if the magnitude is correct, replace the value, or clear it.", "error")
            if rule.get("unique") and duplicates.loc[index]:
                add("rule_unique", index, "Your column rule requires unique values.")
            if rule.get("allowed") and str(value) not in rule["allowed"]:
                add("rule_allowed", index, "Value is outside your exact allowed-value list.")
            if rule.get("pattern") and not fnmatch.fnmatchcase(str(value), rule["pattern"]):
                add("rule_pattern", index, "Value does not match your wildcard pattern (* any text, ? one character, [0-9] a digit).")
            if rule.get("minimum") or rule.get("maximum"):
                try:
                    number = number_for(value, rule)
                    if (rule.get("minimum") and number < Decimal(rule["minimum"])) or (rule.get("maximum") and number > Decimal(rule["maximum"])):
                        add("rule_range", index, "Value is outside your declared numeric range (percentage bounds use points).")
                except ValueError:
                    add("rule_range", index, "Cannot evaluate your numeric range for this value.")
            if rule.get("date_min") or rule.get("date_max"):
                try:
                    known_format = date_formats.get((name, int(index)))
                    value_date = parse_formatted_date(value, source_format=known_format).date().isoformat() if known_format else declared_date(value, rule).isoformat()
                    if (rule.get("date_min") and value_date < rule["date_min"]) or (rule.get("date_max") and value_date > rule["date_max"]):
                        add("rule_date_range", index, "Date is outside your declared range.")
                except ValueError:
                    add("rule_date_range", index, "Cannot evaluate your date range without a valid, unambiguous date.")
        column["rule_findings"] = list(findings.values())
        column["issues"].extend(findings.values())
    # Store column annotations once per revision; page navigation only slices this cache.
    record["workflow_raw_profile"] = copy.deepcopy(report)
    annotations = record.get("workflow_annotations", {}).copy() if changed is not None else {}
    duplicate_rows = set(df.index[df.duplicated()])
    for name in df.columns:
        check()
        if changed is not None and name not in changed and isinstance(annotations.get(name), list):
            annotations[name] = {int(index): row[0] for index, row in zip(df.index, annotations[name]) if row[0]}
        if changed is not None and name not in changed and isinstance(annotations.get(name), dict):
            # Data edits can change dataset-wide duplicate flags in other columns.
            cached = {index: [item for item in cell if item["kind"] != "duplicate"] for index, cell in annotations[name].items()}
            for index in duplicate_rows:
                value = str(scalar(df.at[index, name]))
                accepted = any(entry["column"] == name and entry["issue"] in ("*", "duplicate") and (entry.get("row_index") is None or entry["row_index"] == int(index)) and (entry.get("value") is None or entry["value"] == value) for entry in (*accepted_by_cell.get((name, None), []), *accepted_by_cell.get((name, int(index)), [])))
                if not accepted: cached.setdefault(int(index), []).append({"kind":"duplicate", "message":"This row duplicates an earlier row. Review before removing duplicate rows.", "classification":"review"})
            annotations[name] = {index: cell for index, cell in cached.items() if cell}
            continue
        rows = workflow_annotations(df, report, df[[name]], [name], accepted_findings)
        annotations[name] = {int(index): row[0] for index, row in zip(df.index, rows) if row[0]}
    # A generated date keeps its known order even if its printed form is ambiguous.
    for (column,index),fmt in date_formats.items():
        if column in annotations and index in annotations[column]:
            annotations[column][index]=[flag for flag in annotations[column][index] if flag["kind"] not in ("ambiguous_date","date_format")]
            if not annotations[column][index]:del annotations[column][index]
    # Reevaluate relational and statistical checks after any involved column changes.
    # Cached annotations must never retain old cross-column results.
    custom_kinds = {"cross_column", "outlier"}
    for name, cells in annotations.items():
        annotations[name] = {index: [flag for flag in flags if flag["kind"] not in custom_kinds] for index, flags in cells.items()}
        annotations[name] = {index: flags for index, flags in annotations[name].items() if flags}
    custom = []
    if record.get("cross_column_rules"):
        from .cross_column import findings
        custom.extend(findings(record, check))
    if record.get("outlier_rules"):
        from .outlier_review import findings
        custom.extend(findings(record, check))
    custom_counts = {}
    for finding in custom:
        name, index = finding["column"], finding["row_index"]
        if name not in df or index not in df.index:
            continue
        accepted = (*accepted_by_cell.get((name, None), []), *accepted_by_cell.get((name, index), []))
        if any(item["issue"] in ("*", finding["kind"]) and (item.get("value") is None or item["value"] == str(scalar(df.at[index, name]))) for item in accepted):
            continue
        flags = annotations[name].setdefault(index, [])
        if any(flag["kind"] == finding["kind"] and flag["message"] == finding["message"] for flag in flags):
            continue
        flags.append({"kind": finding["kind"], "message": finding["message"], "classification": "review" if finding["kind"] == "outlier" else "invalid"})
        custom_counts.setdefault((name, finding["kind"]), set()).add(index)
    for column in report["columns"]:
        column["issues"] = [issue for issue in column["issues"] if issue["issue"] not in custom_kinds]
        for kind in custom_kinds:
            indices = custom_counts.get((column["column_name"], kind), set())
            if indices:
                column["issues"].append({"issue": kind, "column": column["column_name"], "count": len(indices), "examples": [scalar(df.at[index, column["column_name"]]) for index in sorted(indices)[:5]]})
    # Summary counts reflect ignored findings too, not just the visible cell markers.
    kinds = {"data_format":"data_format", "invalid_data_format":"invalid_data_format", "time_format":"time", "invalid_time":"invalid_time", "duration_format":"duration", "invalid_duration":"invalid_duration", "missing_values":"missing", "invalid_dates":"invalid_date", "ambiguous_dates":"ambiguous_date", "date_format_inconsistency":"date_format", "case_inconsistency":"capitalization", "extra_whitespace":"whitespace", "currency_inconsistency":"currency", "percentage_inconsistency":"percentage", "symbol_inconsistency":"symbol", "phone_inconsistency":"phone", "invalid_phone":"phone", "type_mismatch":"type", "boolean_inconsistency":"boolean", "invalid_email":"email"}
    for column in report["columns"]:
        counts = {}
        for cell in annotations[column["column_name"]].values():
            for item in cell: counts[item["kind"]] = counts.get(item["kind"], 0) + 1
        for issue in column["issues"]:
            issue["count"] = counts.get(kinds.get(issue["issue"], issue["issue"]), 0 if issue["issue"] in kinds or issue["issue"] == "odd_value" or issue["issue"].startswith("rule_") else issue["count"])
        column["issues"] = [issue for issue in column["issues"] if issue["count"]]
        marker_count = counts.get("missing_marker", 0)
        column["missing_marker_review"] = {"count":marker_count,"examples":list(dict.fromkeys(str(df.at[index,column["column_name"]]) for index, flags in annotations[column["column_name"]].items() if any(flag["kind"]=="missing_marker" for flag in flags)))[:8]}
        if marker_count:
            column["issues"].append({"issue":"missing_marker", "count":marker_count,"examples":column["missing_marker_review"]["examples"],"column":column["column_name"]})
    report["issue_count"] = sum(len(c["issues"]) for c in report["columns"])
    record["editor_profile"] = report
    record["analysis_schema_version"] = ANALYSIS_SCHEMA_VERSION
    record["workflow_annotations"] = annotations
    for column in report["columns"]:
        column["imputation_readiness"] = readiness_from_annotations(record, column["column_name"])
    record["issue_overview"] = {
        "columns": sum(bool(cells) for cells in annotations.values()),
        "cells": sum(len(cells) for cells in annotations.values()),
        "types": len({item["kind"] for cells in annotations.values() for cell in cells.values() for item in cell}),
        "flags": sum(len(cell) for cells in annotations.values() for cell in cells.values()),
    }
    record.pop("editor_issue_navigation", None)
    return report


def apply_decision(record, decision, step_id=None, revision=None, check=lambda: None, *, enforce_imputation_readiness=True):
    decision = Decision(**decision).model_dump()
    check()
    before = record["editor_df"]
    warnings = []
    detail = {}
    date_rows = None
    interpreted_dates = 0
    guarded_fill = False
    kind = decision["kind"]
    column = decision["column"]
    if column and column not in before:
        raise ValueError(f"Unknown column: {column}")
    if kind == "quality":
        from .quality_tools import apply
        after, quality = apply(record, decision["settings"], check, enforce_imputation_readiness=enforce_imputation_readiness)
        tool = decision["settings"]["tool"]
        column = decision["settings"].get("target", decision["settings"].get("column", ""))
        detail["quality"] = quality
        warnings = quality.get("warnings", [])
        if tool == "model_imputation":
            detail["imputation"] = quality
            guarded_fill = enforce_imputation_readiness
    elif kind == "negative_policy":
        record.setdefault("column_rules", {}).setdefault(column, {}).update(decision["settings"])
        after = before
    elif kind == "missing_markers":
        after = before.copy(deep=True).astype(object)
        if decision["settings"]["convert"]:
            after[column] = after[column].map(lambda value: None if isinstance(value,str) and value.strip() and value.strip().casefold() in DEFAULT_MARKERS else value)
        record.setdefault("missing_marker_policies", {})[column] = decision["settings"]
    elif kind == "preparation":
        after = prepare(before, decision["settings"], check)
        record["preparation_settings"] = decision["settings"]
    elif kind == "rules":
        record.setdefault("column_rules", {})[column] = decision["settings"]
        after = before
    elif kind == "rename":
        target = decision["settings"]["name"]
        if target in before.columns:
            raise ValueError("This column name already exists")
        after = before.rename(columns={column: target})
        for key in ("column_rules", "missing_marker_policies"):
            if column in record.get(key, {}): record[key][target] = record[key].pop(column)
        overrides = (record.get("preparation_settings") or {}).get("columns", {})
        if column in overrides: overrides[target] = overrides.pop(column)
        for finding in record.get("ignored_findings", []):
            if finding["column"] == column: finding["column"] = target
        for rule in record.get("cross_column_rules", []):
            for key in ("target", "left", "right", "condition_column"):
                if rule.get(key) == column: rule[key] = target
        if column in record.get("outlier_rules", {}):
            record["outlier_rules"][target] = record["outlier_rules"].pop(column)
            record["outlier_rules"][target]["column"] = target
        for rule in record.get("outlier_rules", {}).values():
            rule["group_by"] = [target if name == column else name for name in rule.get("group_by", [])]
        # Kept outlier signatures intentionally expire when rule names change.
        for finding in record.get("outlier_acceptances", []):
            if finding["column"] == column: finding["column"] = target
        record.pop("workflow_raw_profile", None)
        record.pop("workflow_annotations", None)
    elif kind == "ignore":
        if decision["row_index"] is not None and decision["row_index"] not in before.index:
            raise ValueError("The selected row no longer exists")
        record.setdefault("ignored_findings", []).append({k: decision[k] for k in ("column", "issue", "row_index", "value", "reason")})
        after = before
    else:
        body = EditorRequest(**decision["body"])
        if body.action == "impute_missing_values" and body.parameters.get("method", "mode") != "preserve":
            if enforce_imputation_readiness:
                ensure_imputation_ready(record, body.column, check)
                guarded_fill = True
        if settings_for(record).get(body.column, {}).get("type") == "identifier" and body.action not in ("replace", "trim_whitespace", "remove_duplicates"):
            raise ValueError("Declared identifiers are protected from automatic numeric/date/case conversions")
        token = ACTIVE_MARKERS.set(marker_set(settings_for(record).get(body.column, {}).get("markers")))
        try:
            if body.action == "replace" and body.scope == "issue_columns":
                columns = body.parameters["columns"]
                if any(name not in before.columns for name in columns):
                    raise ValueError("A selected column no longer exists")
                if any(settings_for(record).get(name, {}).get("type") == "identifier" or next((column.get("detected_type") for column in record["editor_profile"]["columns"] if column["column_name"] == name), "") == "identifier" for name in columns):
                    raise ValueError("Identifiers are protected from cross-column issue replacements; edit them individually")
                if record.get("_workflow_dirty") or not record.get("workflow_annotations"):
                    profile_record(record, check)
                after = before.copy(deep=True).astype(object)
                for name in columns:
                    check()
                    cells = record["workflow_annotations"].get(name, {})
                    indices = [index for index, flags in cells.items() if any(flag["kind"] == body.parameters["issue_kind"] for flag in flags)]
                    if name == body.column and body.row_index not in indices:
                        raise ValueError("The selected cell no longer has this issue. Review the current sheet again.")
                    after.loc[indices, name] = body.value
                warnings = ["Only the selected issue type in your explicitly selected columns is replaced. Other values and columns are preserved."]
            elif body.action == "replace" and body.scope == "issue":
                cells = record.get("workflow_annotations", {}).get(body.column)
                if cells is None:
                    cells = workflow_annotations(before, record["editor_profile"], before[[body.column]], [body.column], record.get("ignored_findings"))
                entries = cells.items() if isinstance(cells, dict) else ((int(index), row[0]) for index, row in zip(before.index, cells))
                indices = [index for index, cell in entries if any(item["kind"] == body.parameters["issue_kind"] for item in cell)]
                if body.row_index not in indices:
                    raise ValueError("The selected cell no longer has this issue")
                after = before.copy(deep=True).astype(object)
                after.loc[indices, body.column] = body.value
            else:
                runtime_body=body
                if body.action=="impute_missing_values":
                    sources={index:fmt for (name,index),fmt in known_date_formats(record).items() if name==body.column}
                    excluded=[index for name,index in estimated_cells(record) if name==body.column]
                    runtime_body=body.model_copy(update={"parameters":{**body.parameters,"_source_formats":sources,"_excluded_rows":excluded}})
                if body.action=="normalize_dates":
                    sources={index:fmt for (name,index),fmt in known_date_formats(record).items() if name==body.column}
                    runtime_body=body.model_copy(update={"parameters":{**body.parameters,"_source_formats":sources}})
                    date_rows=[]
                    for index,value in before[body.column].items():
                        if body.scope=="cell" and int(index)!=body.row_index or missing(value):continue
                        try:
                            parse_formatted_date(value,body.parameters.get("interpretation"),sources.get(int(index)))
                            date_rows.append(int(index))
                            if int(index) not in sources and body.parameters.get("interpretation") in ("day_first", "month_first") and is_ambiguous_numeric_date(value):
                                interpreted_dates += 1
                        except (ValueError,TypeError,OverflowError):pass
                after, detail = propose(before, runtime_body, record.get("editor_profile"))
                warnings = detail.get("warnings", [])
        finally:
            ACTIVE_MARKERS.reset(token)
        if body.action == "replace" and enforce_imputation_readiness:
            targets = body.parameters["columns"] if body.scope == "issue_columns" else [body.column]
            for name in targets:
                check()
                if before[name].equals(after[name]):
                    continue
                if (before[name].map(actual_empty) & ~after[name].map(actual_empty)).any():
                    ensure_imputation_ready(record, name, check)
                    guarded_fill = True
        column = body.column
    check()
    step_id = step_id or str(uuid.uuid4())
    revision = record["editor_revision"] + 1 if revision is None else revision
    action = kind if kind != "fix" else "unify_text_values" if decision["body"].get("scope") == "values" else decision["body"]["action"]
    if kind == "quality":
        tool = decision["settings"]["tool"]
        action = "impute_missing_values" if tool == "model_imputation" else "merge_records" if tool == "record_matching" and decision["settings"].get("action") == "merge" else "keep_records" if tool == "record_matching" else "cross_column_" + decision["settings"].get("action", "save_rules") if tool == "cross_column" else "outlier_" + decision["settings"].get("action", "review")
    if kind == "missing_markers": action = "normalize_missing_values" if decision["settings"]["convert"] else "keep_missing_labels"
    changes = ([{"step_id":step_id,"revision":revision,"action":"rename_column","column":column,"row_index":-1,"spreadsheet_row":1,"before":column,"after":decision["settings"]["name"],"removed_row":False}] if kind == "rename" else diff(before, after, action, revision, step_id, check))
    if kind == "rename": action = "rename_column"
    affected = len(before.index.difference(after.index)) if action == "remove_duplicates" else len(changes)
    record["editor_df"] = after
    dirty = set(record.get("_workflow_dirty", []))
    dirty.update(before.columns if kind == "preparation" or not before.index.equals(after.index) else {item["column"] for item in changes} if kind == "quality" or decision.get("body", {}).get("scope") == "issue_columns" else [column, *after.columns.difference(before.columns)])
    record["_workflow_dirty"] = list(dirty)
    entry = {"id": step_id, "action": action, "column": column or "All columns", "scope": decision["body"].get("scope", "dataset" if kind == "preparation" else "column"), "parameters": decision["settings"] if kind in ("rules", "preparation", "rename", "missing_markers", "negative_policy") else decision["body"].get("parameters", {}) if kind == "fix" else {"issue": decision["issue"], "reason": decision["reason"], "row_index": decision["row_index"]}, "revision": revision, "changed_cells": affected, "examples": changes[:10], "warnings": [], "decision": decision}
    if kind == "quality":
        entry["parameters"] = decision["settings"]
        entry["scope"] = "dataset" if tool in ("cross_column", "record_matching") else "column"
        entry["quality"] = detail["quality"]
        entry["removed_rows"] = len(before.index.difference(after.index))
    if kind == "fix" and decision["body"].get("scope") == "issue_columns":
        entry["column"] = ", ".join(decision["body"]["parameters"]["columns"])
    if action in ("replace", "unify_text_values") or action == "impute_missing_values" and decision["body"].get("parameters", {}).get("method") == "constant":
        warnings = ["Your entered value is accepted in the changed cells and will not be highlighted as an issue while it remains unchanged. It is not independently verified."]
    if date_rows is not None:
        entry["date_format_rows"] = date_rows
        entry["interpreted_dates"] = interpreted_dates
    if detail.get("imputation"): entry["imputation"] = detail["imputation"]
    record.setdefault("editor_changes", []).append(entry)
    entry["warnings"] = warnings
    saved_step = {"id": step_id, "decision": decision, "revision": revision}
    if guarded_fill:
        saved_step["imputation_readiness_policy"] = IMPUTATION_READINESS_POLICY
        entry["imputation_readiness_policy"] = IMPUTATION_READINESS_POLICY
    record.setdefault("workflow_steps", []).append(saved_step)
    record.setdefault("complete_changes", []).extend(changes)
    record["editor_revision"] = revision

    return entry


def reconcile_imputation_audits(record):
    by_step={}
    for change in record.get("complete_changes",[]): by_step.setdefault(change["step_id"],[]).append(change)
    repaired=False
    for entry in record.get("editor_changes",[]):
        audit=entry.get("imputation")
        if not audit or entry.get("id") not in by_step: continue
        actual=[c for c in by_step[entry["id"]] if not c.get("removed_row") and missing(c.get("before")) and not missing(c.get("after"))]
        actual_rows=sorted({int(c["row_index"]) for c in actual})
        if audit.get("imputed_count")==len(actual_rows) and {int(c["row_index"]) for c in audit.get("imputed_cells",[])}==set(actual_rows): continue
        audit.update(imputed_count=len(actual_rows),imputed_cells=[{"row_index":i,"spreadsheet_row":i+2,"is_imputed":True} for i in actual_rows],missing_after=max(0,audit.get("missing_before",0)-len(actual_rows)),distribution_after={})
        note="Earlier imputation counts were reconciled with actual cell changes. Unreliable historical after-distribution statistics were omitted."
        audit.setdefault("warnings",[]).append(note);entry.setdefault("warnings",[]).append(note)
        repaired=True
    return repaired


def ensure_workflow(record):
    if record.get("workflow_version"):
        if reconcile_imputation_audits(record): record["_audit_repaired"]=True
        return
    # Existing work is an immutable migration baseline; never reinterpret or discard it.
    record["workflow_version"] = 1
    record["workflow_steps"] = []
    record["complete_changes"] = []
    record["workflow_base"] = {key: copy.deepcopy(record.get(key)) for key in ("editor_df", "editor_changes", "column_rules", "preparation_settings", "ignored_findings", "missing_marker_policies", "cross_column_rules", "outlier_rules", "outlier_acceptances", "kept_record_pairs")}
    record["legacy_history_notice"] = "Earlier confirmed work is preserved as the migration baseline. Complete per-cell audit and new undo start with the enhanced workflow. Legacy sample-only steps are not included in the complete change log." if record.get("editor_changes") or record.get("editor_basic_log") else ""


def replay_without(record, step_id, check=lambda: None):
    steps = record["workflow_steps"]
    removed_ids = set(step_id) if isinstance(step_id, list) else {step_id}
    if not removed_ids or not removed_ids.issubset({step["id"] for step in steps}):
        raise ValueError("This step belongs to the preserved baseline or has already been removed")
    revision = record["editor_revision"] + 1
    base = record["workflow_base"]
    # Older working copies predate these optional tools. Undo still starts clean.
    for key in ("cross_column_rules", "outlier_rules", "outlier_acceptances", "kept_record_pairs"):
        record.pop(key, None)
    for key, value in base.items():
        record[key] = copy.deepcopy(value) if value is not None else {} if key in ("column_rules", "missing_marker_policies", "outlier_rules") else [] if key in ("ignored_findings", "editor_changes", "cross_column_rules", "outlier_acceptances", "kept_record_pairs") else None
    record["workflow_steps"] = []; record["complete_changes"] = []
    # Final-revision annotations cannot be reused against the restored baseline.
    # In particular, accepted issue-wide replacements have removed their flags.
    for cache in ("workflow_annotations", "workflow_raw_profile", "editor_issue_navigation", "issue_overview"):
        record.pop(cache, None)
    record["_workflow_dirty"] = list(record["editor_df"].columns)
    profile_record(record, check)
    try:
        for step in steps:
            check()
            if step["id"] not in removed_ids:
                body = step["decision"].get("body", {})
                if body.get("scope") in ("issue", "invalid_dates", "issue_columns") and record.get("_workflow_dirty"):
                    profile_record(record, check)
                entry = apply_decision(record, step["decision"], step["id"], step["revision"], check,
                                       enforce_imputation_readiness=step.get("imputation_readiness_policy") == IMPUTATION_READINESS_POLICY)
                if step.get("automatic_run"):
                    record["workflow_steps"][-1]["automatic_run"] = step["automatic_run"]
                    entry["automatic_run"] = step["automatic_run"]
    except ValueError as exc:
        raise ValueError(f"Cannot undo safely: a later step depends on it. Undo the dependent step first. {exc}") from exc
    record["editor_revision"] = revision
    record["_workflow_dirty"] = list(record["editor_df"].columns)


def recipe_from(record, name="My cleaning recipe"):
    steps = []
    for step in record.get("workflow_steps", []):
        decision = copy.deepcopy(step["decision"])
        if decision["kind"] == "quality":
            continue  # Record merges, fitted models and row judgements need a fresh review.
        if decision["kind"] == "ignore":
            continue  # Row-specific judgements do not transfer to another dataset.
        if decision["kind"] == "fix":
            body = decision["body"]
            if body["scope"] not in ("column", "values", "invalid_dates", "issue") or body["action"] == "replace" and body["scope"] != "values":
                continue
        steps.append(decision)
    return Recipe(name=name, steps=steps, source_columns=list(record["df"].columns)).model_dump()


def compatible(record, recipe):
    recipe = Recipe(**recipe).model_dump()
    columns = set(record["editor_df"].columns)
    required = set()
    for step in recipe["steps"]:
        if step["kind"] == "quality":
            raise ValueError("Reviewed quality tools cannot be transferred through a recipe; review them on this dataset")
        if step["kind"] in ("rules", "rename", "missing_markers", "negative_policy"): required.add(step["column"])
        if step["kind"] == "rename": columns.add(step["settings"]["name"])
        if step["kind"] == "preparation": required.update(step["settings"]["columns"])
        if step["kind"] == "fix":
            body = step["body"]
            if body["scope"] == "cell" or body["scope"] == "matching" or body["action"] == "replace" and body["scope"] != "values":
                raise ValueError("Recipes cannot transfer row-specific or issue-clearing replacements")
            required.add(body["column"])
            group = body["parameters"].get("group_by", [])
            required.update([group] if isinstance(group, str) else group)
    return {"missing_columns": sorted(required - columns), "extra_columns": sorted(columns - set(recipe["source_columns"])), "compatible": required.issubset(columns)}


def apply_recipe(record, recipe, check=lambda: None, progress=lambda stage, n: None):
    recipe = Recipe(**recipe).model_dump()
    compatibility = compatible(record, recipe)
    if not compatibility["compatible"]:
        raise ValueError("Missing columns: " + ", ".join(compatibility["missing_columns"]))
    warnings = []
    for number, original in enumerate(recipe["steps"]):
        check(); step = copy.deepcopy(original)
        progress(f"Recipe step {number + 1} of {len(recipe['steps'])}", number)
        if step["kind"] == "fix":
            body = step["body"]; df = record["editor_df"]
            body["revision"] = record["editor_revision"]
            if df.empty: raise ValueError("No rows remain for this recipe step")
            body["row_index"] = int(df.index[0])
            if body["scope"] == "values":
                present = set(v for v in df[body["column"]] if isinstance(v, str))
                sources = body["parameters"]["source_values"]
                absent = set(sources) - present
                if absent: warnings.append({"column": body["column"], "unmatched_values": sorted(absent)})
                unseen = present - set(sources) - {body["value"]}
                if unseen: warnings.append({"column": body["column"], "unmapped_values_preserved": sorted(unseen)[:50], "unmapped_value_count": len(unseen)})
                # Keep only applicable mappings; a single surviving alias still needs mapping.
                if not any(v in present and v != body["value"] for v in sources):
                    continue
                body["parameters"]["allow_absent_recipe_values"] = True
        apply_decision(record, step, check=check)
    record["recipe_version"] = recipe["version"]
    record["recipe_name"] = recipe["name"]
    return {**compatibility, "mapping_warnings": warnings, "imputation": "Mean/median/mode are recalculated on this file; constant values remain fixed."}


def suggested_groups(entries):
    # Bounded local suggestion search. No semantic equivalence is assumed.
    values = [entry["value"] for entry in entries if len(entry["value"]) <= 100][:1000]
    groups, used = [], set()
    for value in values:
        if value in used: continue
        matches = [other for other in values if other not in used and other != value and abs(len(value) - len(other)) <= 3 and SequenceMatcher(None, value.casefold(), other.casefold()).ratio() >= .78]
        if matches:
            group = [value, *matches[:15]]; used.update(group)
            groups.append({"values": group, "suggested": value})
        if len(groups) >= 30: break
    return groups

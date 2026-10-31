"""Reviewed relationships between columns. Expressions are structured, never evaluated.

Rules only flag discrepancies. Recalculation and clearing require a separate,
explicit action and always return a new frame for the workflow's atomic commit.
"""
import copy
import math
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext

from .common import missing, scalar
from .date_analyzer import parse_formatted_date

_OPERATORS = {"eq", "ne", "lt", "le", "gt", "ge"}
_ARITHMETIC = {"add", "subtract", "multiply", "divide"}
_RULE_KEYS = {"id", "label", "kind", "target", "left", "right", "operator", "arithmetic", "tolerance", "value_type", "interpretation", "condition_column", "condition_value"}
_NUMBER = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _text(value, label, limit=200, allow_empty=False):
    if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be {'at most' if allow_empty else 'between 1 and'} {limit} characters")
    return value


def validate_settings(settings):
    """Validate serializable settings independently of the current data frame."""
    if not isinstance(settings, dict):
        raise ValueError("Choose cross-column rule settings")
    action = settings.get("action", "save_rules")
    if action not in ("save_rules", "recalculate", "clear"):
        raise ValueError("Choose save rules, recalculate, or clear")
    allowed = {"action", "rules"} if action == "save_rules" else {"action", "rule_id", "row_indices"}
    if set(settings) - allowed:
        raise ValueError("Unsupported cross-column settings")
    if action != "save_rules":
        result = {"action": action, "rule_id": _text(settings.get("rule_id"), "Select a rule", 80)}
        rows = settings.get("row_indices")
        if rows is not None:
            if not isinstance(rows, list) or len(rows) > 100000 or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in rows):
                raise ValueError("Select valid spreadsheet rows")
            rows = sorted(set(rows))
            if not rows:
                raise ValueError("Select at least one row, or choose all affected rows")
        result["row_indices"] = rows
        return result
    rules = settings.get("rules", [])
    if not isinstance(rules, list) or len(rules) > 30:
        raise ValueError("Use at most 30 cross-column rules")
    result, identifiers = [], set()
    for index, raw in enumerate(rules):
        if not isinstance(raw, dict) or set(raw) - _RULE_KEYS:
            raise ValueError("Rules must use the supported column relationship fields")
        rule = copy.deepcopy(raw)
        rule["id"] = _text(rule.get("id", f"rule-{index + 1}"), "Rule ID", 80)
        if rule["id"] in identifiers:
            raise ValueError("Each cross-column rule needs a unique ID")
        identifiers.add(rule["id"])
        rule["label"] = _text(rule.get("label", f"Rule {index + 1}"), "Rule name", 160)
        rule["target"] = _text(rule.get("target"), "Target column")
        if rule.get("kind") not in ("compare", "arithmetic", "required_if"):
            raise ValueError("Choose a comparison, calculation, or conditional required value")
        if rule["kind"] == "required_if":
            rule["condition_column"] = _text(rule.get("condition_column"), "Condition column")
            rule["condition_value"] = _text(rule.get("condition_value", ""), "Condition value", 1000, True)
            rule["operator"] = rule.get("operator", "eq")
            if rule["operator"] not in ("eq", "ne"):
                raise ValueError("Conditional required rules support equals or does not equal")
            if rule["target"] == rule["condition_column"]:
                raise ValueError("Use a different condition column")
        else:
            rule["left"] = _text(rule.get("left"), "Comparison or first operand column")
            rule["value_type"] = rule.get("value_type", "numeric")
            rule["interpretation"] = rule.get("interpretation", "preserve")
            if rule["interpretation"] not in ("preserve", "day_first", "month_first"):
                raise ValueError("Choose a valid date interpretation")
            if rule["value_type"] not in ("numeric", "date", "text"):
                raise ValueError("Choose numeric, date, or text comparison")
            if rule["target"] == rule["left"]:
                raise ValueError("Use a different operand column from the target")
            tolerance = rule.get("tolerance", 0)
            if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance < 0 or tolerance > 1e100 or not math.isfinite(tolerance):
                raise ValueError("Tolerance must be a finite nonnegative number")
            rule["tolerance"] = tolerance
            if rule["kind"] == "arithmetic":
                rule["right"] = _text(rule.get("right"), "Second operand column")
                rule["arithmetic"] = rule.get("arithmetic", "multiply")
                if rule["arithmetic"] not in _ARITHMETIC or rule["value_type"] != "numeric":
                    raise ValueError("Choose a numeric add, subtract, multiply, or divide relationship")
                if rule["target"] == rule["right"]:
                    raise ValueError("The calculated target cannot also be an operand")
            else:
                rule["operator"] = rule.get("operator", "eq")
                if rule["operator"] not in _OPERATORS:
                    raise ValueError("Choose a valid comparison operator")
                if rule["value_type"] != "numeric" and tolerance:
                    raise ValueError("Tolerance is available for numeric comparisons only")
        result.append(rule)
    return {"action": "save_rules", "rules": result}


def _rules(record, settings):
    return settings["rules"] if settings["action"] == "save_rules" else validate_settings({"rules": record.get("cross_column_rules", [])})["rules"]


def _column_settings(record):
    # Lazy imports avoid a circular dependency when workflow integrates this tool.
    from .workflow import settings_for
    return settings_for(record)


def _validate_columns(record, rules):
    from .type_detector import detect_column_type
    df = record["editor_df"]
    configured = _column_settings(record)
    profile = {c["column_name"]: c.get("detected_type") for c in record.get("editor_profile", {}).get("columns", [])}
    cache = {}
    for rule in rules:
        columns = [rule["target"], rule["condition_column"]] if rule["kind"] == "required_if" else [rule["target"], rule["left"], *([rule["right"]] if rule["kind"] == "arithmetic" else [])]
        for column in columns:
            if column not in df.columns:
                raise ValueError(f'Rule "{rule["label"]}": unknown column "{column}"')
            if rule["kind"] != "required_if" and rule["value_type"] in ("numeric", "date"):
                if column not in cache:
                    cache[column] = configured.get(column, {}).get("type") or profile.get(column) or detect_column_type(df[column])["type"]
                if cache[column] == "identifier":
                    raise ValueError(f'Column "{column}" is a protected identifier. Use text comparison instead')
    return configured


def _plain_number(value):
    # No implicit currency, percent scale, locale, or unit conversion in equations.
    if isinstance(value, bool) or len(str(value)) > 1200 or not _NUMBER.fullmatch(str(value).strip()):
        raise ValueError("requires a plain number; standardize units or percentage scale first")
    try:
        result = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("requires a finite number") from exc
    if not result.is_finite() or len(result.as_tuple().digits) > 100 or abs(result.as_tuple().exponent) > 1000:
        raise ValueError("number exceeds supported precision or range")
    return result


def _render_number(value):
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _date(value, rule, source_format):
    parsed = parse_formatted_date(value, rule["interpretation"], source_format)
    if isinstance(parsed, date) and not isinstance(parsed, datetime):
        parsed = datetime.combine(parsed, datetime.min.time())
    return parsed


def _compare(left, right, operator, tolerance=Decimal(0)):
    if operator == "eq":
        return abs(left - right) <= tolerance if isinstance(left, Decimal) else left == right
    if operator == "ne":
        return abs(left - right) > tolerance if isinstance(left, Decimal) else left != right
    return {"lt": lambda: left < right, "le": lambda: left <= right, "gt": lambda: left > right, "ge": lambda: left >= right}[operator]()


def _evaluate(record, rules, check):
    df = record["editor_df"]
    configured = _validate_columns(record, rules)
    from .workflow import known_date_formats
    date_formats = known_date_formats(record) if any(r.get("value_type") == "date" for r in rules) else {}
    results = []

    def blank(value, column):
        return missing(value, configured.get(column, {}).get("markers"))

    for rule in rules:
        check()
        target = rule["target"]
        for index in df.index:
            if int(index) % 128 == 0:
                check()
            value = df.at[index, target]
            expected, repairable, problem = None, False, None
            status = "mismatch"
            if rule["kind"] == "required_if":
                conditional = df.at[index, rule["condition_column"]]
                condition_text = "" if blank(conditional, rule["condition_column"]) else str(scalar(conditional))
                matches = condition_text == rule["condition_value"]
                if rule["operator"] == "ne":
                    matches = not matches
                if not matches or not blank(value, target):
                    continue
                problem, status = "A value is required by this condition", "missing_target"
            else:
                try:
                    operand_columns = [rule["left"]] + ([rule["right"]] if rule["kind"] == "arithmetic" else [])
                    operands = []
                    for column in operand_columns:
                        operand = df.at[index, column]
                        if blank(operand, column):
                            raise ValueError(f'operand "{column}" is empty')
                        try:
                            operands.append(_plain_number(operand) if rule["value_type"] == "numeric" else _date(operand, rule, date_formats.get((column, int(index)))) if rule["value_type"] == "date" else str(scalar(operand)))
                        except (ValueError, TypeError, OverflowError) as exc:
                            raise ValueError(f'operand "{column}": {exc}') from exc
                    if rule["kind"] == "arithmetic":
                        a, b = operands
                        if rule["arithmetic"] == "divide" and b == 0:
                            raise ValueError(f'operand "{rule["right"]}" is zero; division is undefined')
                        with localcontext() as context:
                            context.prec = max(50, len(a.as_tuple().digits) + len(b.as_tuple().digits) + 20)
                            number = {"add": lambda: a + b, "subtract": lambda: a - b, "multiply": lambda: a * b, "divide": lambda: a / b}[rule["arithmetic"]]()
                        if not number.is_finite():
                            raise ValueError("the calculation is not finite")
                        expected, repairable = _render_number(number), True
                        if blank(value, target):
                            status, problem = "missing_target", f"Calculated value is missing; expected {expected}"
                        else:
                            try:
                                actual = _plain_number(value)
                            except (ValueError, TypeError, OverflowError) as exc:
                                status, problem = "invalid_target", str(exc)
                            else:
                                if _compare(actual, number, "eq", Decimal(str(rule["tolerance"]))):
                                    continue
                                problem = f"Value does not match the calculation; expected {expected}"
                    else:
                        if blank(value, target):
                            raise ValueError(f'target "{target}" is empty')
                        actual = _plain_number(value) if rule["value_type"] == "numeric" else _date(value, rule, date_formats.get((target, int(index)))) if rule["value_type"] == "date" else str(scalar(value))
                        other = operands[0]
                        if rule["value_type"] == "date" and (actual.tzinfo is None) != (other.tzinfo is None):
                            raise ValueError("date comparison mixes timezone-aware and timezone-naive values")
                        if _compare(actual, other, rule["operator"], Decimal(str(rule["tolerance"]))):
                            continue
                        expected = scalar(other)
                        problem = f'Target must satisfy {rule["operator"]} against "{rule["left"]}"'
                except (ValueError, TypeError, OverflowError, ArithmeticError) as exc:
                    status, problem, repairable = "uncheckable", str(exc), False
            results.append({"kind": "cross_column", "rule_id": rule["id"], "rule_label": rule["label"], "column": target, "row_index": int(index), "spreadsheet_row": int(index) + 2, "before": scalar(value), "expected": expected, "repairable": repairable, "status": status, "message": f'Rule "{rule["label"]}", column "{target}", spreadsheet row {int(index) + 2}: {problem}'})
    return results


def _review(record, settings, check, full=False):
    settings = validate_settings(settings)
    rules = _rules(record, settings)
    if settings["action"] != "save_rules":
        rules = [rule for rule in rules if rule["id"] == settings["rule_id"]]
        if not rules:
            raise ValueError("This cross-column rule no longer exists")
    flags = _evaluate(record, rules, check)
    if settings["action"] != "save_rules" and settings["row_indices"] is not None:
        indices = set(settings["row_indices"])
        if not indices.issubset(set(map(int, record["editor_df"].index))):
            raise ValueError("A selected spreadsheet row no longer exists")
        flags = [flag for flag in flags if flag["row_index"] in indices]
    counts = Counter(flag["rule_id"] for flag in flags)
    repairable = sum(flag["repairable"] for flag in flags)
    return {"rules": copy.deepcopy(rules), "findings": flags if full else flags[:500], "findings_truncated": len(flags)>500, "finding_count": len(flags), "affected_cells": len({(flag["column"], flag["row_index"]) for flag in flags}), "repairable_count": repairable, "uncheckable_count": sum(flag["status"] == "uncheckable" for flag in flags), "rule_counts": dict(counts), "warnings": ["Rules flag relationships for review; no value changes until you explicitly recalculate or clear."] + (["Showing the first 500 findings. Counts and corrections cover all affected rows."] if len(flags)>500 else [])}


def review(record, settings, check=lambda: None):
    return _review(record, settings, check)


def findings(record, check=lambda: None):
    """Persistent issue flags for the current values; never mutate the record."""
    rules = validate_settings({"rules": record.get("cross_column_rules", [])})["rules"]
    return _evaluate(record, rules, check) if rules else []


def apply(record, settings, check=lambda: None):
    settings = validate_settings(settings)
    detail = _review(record, settings, check, full=True)
    before = record["editor_df"]
    if settings["action"] == "save_rules":
        check()
        record["cross_column_rules"] = copy.deepcopy(settings["rules"])
        return before.copy(deep=True), {**detail, "findings": detail["findings"][:500], "changed_cells": 0}
    rule = detail["rules"][0]
    if settings["action"] == "recalculate" and rule["kind"] != "arithmetic":
        raise ValueError("Only arithmetic relationships offer recalculation")
    if settings["action"] == "clear":
        from .type_detector import detect_column_type
        declared = _column_settings(record).get(rule["target"], {}).get("type")
        if declared == "identifier" or detect_column_type(before[rule["target"]])["type"] == "identifier":
            raise ValueError("Protected identifiers cannot be cleared by a relationship rule")
    eligible = [flag for flag in detail["findings"] if flag["repairable"]] if settings["action"] == "recalculate" else [flag for flag in detail["findings"] if not missing(flag["before"], [""])]
    if not eligible:
        raise ValueError("No affected cells can be recalculated with valid operands" if settings["action"] == "recalculate" else "No nonempty affected cells to clear")
    after = before.copy(deep=True).astype(object)
    for flag in eligible:
        check()
        after.at[flag["row_index"], flag["column"]] = flag["expected"] if settings["action"] == "recalculate" else None
    if settings["action"] == "recalculate":
        # A reviewed equation must not silently break another saved relationship.
        other_rules = [item for item in _rules(record, settings) if item["id"] != rule["id"]]
        if other_rules:
            previous = {(item["rule_id"], item["row_index"]) for item in _evaluate(record, other_rules, check)}
            candidate = {**record, "editor_df": after}
            introduced = [item for item in _evaluate(candidate, other_rules, check) if (item["rule_id"], item["row_index"]) not in previous]
            if introduced:
                conflict = introduced[0]
                raise ValueError(f'Recalculation conflicts with rule "{conflict["rule_label"]}" at column "{conflict["column"]}", spreadsheet row {conflict["spreadsheet_row"]}. Review the rules first')
    return after, {**detail, "findings": detail["findings"][:500], "changed_cells": len(eligible), "skipped_count": len(detail["findings"]) - len(eligible), "warnings": (["Rows with missing, invalid, or ambiguous operands were left unchanged."] if len(eligible) < len(detail["findings"]) else []) + (["Showing the first 500 findings. Counts and corrections cover all affected rows."] if detail["findings_truncated"] else [])}

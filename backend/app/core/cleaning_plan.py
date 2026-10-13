from .profiler import profile_dataframe


def generate_cleaning_plan(df, report=None):
    report = report or profile_dataframe(df)
    plan = []

    def add(column, operation, issue, count, safety, explanation, parameters=None):
        plan.append(
            {
                "id": f"op-{len(plan) + 1}",
                "column": column,
                "operation": operation,
                "issue": issue,
                "parameters": parameters or {},
                "affected_rows": count,
                "explanation": explanation,
                "safety": safety,
                "requires_confirmation": safety != "safe",
                "enabled": safety == "safe",
            }
        )

    for c in report["columns"]:
        name = c["column_name"]
        issues = {i["issue"]: i["count"] for i in c["issues"]}
        if issues.get("extra_whitespace"):
            add(
                name,
                "trim_whitespace",
                "extra_whitespace",
                issues["extra_whitespace"],
                "safe",
                "Trim edges and collapse repeated whitespace.",
            )
        if issues.get("missing_values"):
            add(
                name,
                "normalize_missing_values",
                "missing_values",
                issues["missing_values"],
                "review",
                "Convert approved missing markers to empty cells; no values are invented.",
                {"markers": ["", "null", "none", "n/a", "na", "nan", "-"]},
            )
        if issues.get("case_inconsistency") and c["detected_type"] != "identifier":
            add(
                name,
                "normalize_capitalization",
                "case_inconsistency",
                issues["case_inconsistency"],
                "review",
                "Standardize capitalization. Review acronyms and proper names.",
                {"strategy": "title"},
            )
        kind = c["detected_type"]
        if kind == "currency" or issues.get("currency_inconsistency"):
            add(
                name,
                "normalize_currency",
                "currency_inconsistency",
                c["total_rows"] - c["missing_count"],
                "review",
                "Choose the intended currency and output notation. Bare amounts and ambiguous symbols require explicit confirmation. Other currencies stay unchanged; no currency conversion is performed.",
                {
                    "action": "preserve",
                    "symbol": "",
                    "position": "prefix",
                    "currency": "",
                    "format": "code",
                    "assume_unlabelled": False,
                    "symbol_aliases": [],
                },
            )
        if kind == "percentage" or issues.get("percentage_inconsistency"):
            add(
                name,
                "normalize_percentage",
                "percentage_inconsistency"
                if issues.get("percentage_inconsistency")
                else "percentage_formatting",
                c["total_rows"] - c["missing_count"],
                "review",
                "Choose whether to include %. Confirm whether bare numbers are percentage points (10 = 10%) or fractional ratios (0.1 = 10%). Invalid values stay unchanged.",
                {
                    "action": "preserve",
                    "format": "with_sign",
                    "bare_interpretation": "preserve",
                },
            )
        if (
            kind in ("integer", "decimal")
            and not issues.get("currency_inconsistency")
            and not issues.get("percentage_inconsistency")
        ):
            add(
                name,
                "normalize_numeric",
                "numeric_formatting",
                c["total_rows"] - c["missing_count"],
                "review",
                "Normalize comma grouping and decimal formatting. Invalid values remain unchanged.",
                {"kind": kind},
            )
        if kind == "number_with_symbol":
            add(
                name,
                "normalize_symbols",
                "symbol_inconsistency",
                c["total_rows"] - c["missing_count"],
                "review",
                "Add a chosen symbol to all numeric values, remove all labels, or leave them unchanged. This changes notation only; units are not converted.",
                {"action": "preserve", "symbol": "", "position": "suffix"},
            )
        if kind == "phone":
            add(
                name,
                "normalize_phone",
                "phone_inconsistency",
                c["total_rows"] - c["missing_count"],
                "review",
                "Choose whether to include country codes and +, remove them, or leave numbers unchanged. Local numbers need an explicit country; invalid values stay unchanged.",
                {"action": "preserve", "region": ""},
            )
        if kind == "boolean":
            add(
                name,
                "normalize_boolean",
                "boolean_formatting",
                c["total_rows"] - c["missing_count"],
                "review",
                "Convert recognized boolean labels to true/false; preserve invalid values.",
            )
        if issues.get("invalid_dates"):
            add(
                name,
                "resolve_invalid_dates",
                "invalid_dates",
                issues["invalid_dates"],
                "review",
                "Replace invalid dates with empty cells or correct individual rows. Valid and ambiguous dates are left untouched by this operation.",
                {"action": "manual", "replacements": {}},
            )
        if kind in ("date", "datetime"):
            add(
                name,
                "normalize_dates",
                "date_formatting",
                c["total_rows"] - c["missing_count"],
                "review",
                "Use ISO dates. Ambiguous values stay unchanged unless you choose an interpretation.",
                {"interpretation": "preserve", "include_time": kind == "datetime"},
            )
    for c in report["columns"]:
        if c["missing_count"]:
            info = c["imputation"]
            add(
                c["column_name"],
                "impute_missing_values",
                "missing_values",
                c["missing_count"],
                "review",
                "Imputation: fill only missing cells after approved normalization. Estimates can distort distributions; review the preview and explicitly confirm before applying.",
                {
                    "method": "preserve",
                    "group_by": [],
                    "order_by": "",
                    "single_entity": False,
                    "confirmed": False,
                },
            )
            plan[-1]["recommendation"] = info
    if report["duplicate_rows"]:
        add(
            None,
            "remove_duplicates",
            "duplicate_rows",
            report["duplicate_rows"],
            "destructive",
            "Remove complete duplicate rows. Original upload is retained.",
            {"subset": None},
        )
    return plan

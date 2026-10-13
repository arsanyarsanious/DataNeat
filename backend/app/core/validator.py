from .profiler import profile_dataframe


def validate_cleaning(original, cleaned, logs):
    before, after = profile_dataframe(original), profile_dataframe(cleaned)

    def modified(names):
        return sum(log["modified_values"] for log in logs if log["operation"] in names)

    return {
        "imputed_cells": modified(["impute_missing_values"]),
        "imputation": [
            log for log in logs if log["operation"] == "impute_missing_values"
        ],
        "rows_before": len(original),
        "rows_after": len(cleaned),
        "missing_before": before["missing_count"],
        "missing_after": after["missing_count"],
        "duplicates_removed": len(original) - len(cleaned),
        "dates_standardized": modified(["normalize_dates"]),
        "numeric_values_standardized": modified(
            ["normalize_numeric", "normalize_currency", "normalize_percentage"]
        ),
        "invalid_dates_resolved": modified(["resolve_invalid_dates"]),
        "text_values_modified": modified(
            ["trim_whitespace", "normalize_capitalization"]
        ),
        "modified_values": sum(l["modified_values"] for l in logs),
        "unresolved_issues": after["issue_count"],
        "remaining_issues": [i for c in after["columns"] for i in c["issues"]],
        "before": before,
        "after": after,
    }

import re

from .common import missing, scalar
from .date_analyzer import analyze_date_column
from .imputation import distribution, missing_pattern, recommendation
from .issue_detector import detect_column_issues, detect_duplicates
from .type_detector import detect_column_type


def profile_column(series):
    values = [v for v in series if not missing(v)]
    count = len(series) - len(values)
    detected = detect_column_type(series)
    report = {
        "column_name": str(series.name),
        "total_rows": len(series),
        "missing_count": count,
        "missing_percentage": round(100 * count / len(series), 2) if len(series) else 0,
        "unique_count": len(set(map(str, values))),
        "pandas_dtype": str(series.dtype),
        "sample_values": [scalar(v) for v in values[:5]],
        "detected_type": detected["type"],
        "match_score": detected["match_score"],
        "issues": detect_column_issues(series, detected),
    }
    if count:
        report["imputation"] = recommendation(series, detected["type"])
        report["statistics"] = report["imputation"]["statistics"]
        report["missing_pattern"] = report["imputation"]["missing_pattern"]
    else:
        report["statistics"] = distribution(series)
        report["missing_pattern"] = missing_pattern(series)
    if detected["type"] in ("date", "datetime"):
        report["date_analysis"] = analyze_date_column(series)
        for kind, key in [
            ("ambiguous_dates", "ambiguous"),
            ("invalid_dates", "invalid"),
        ]:
            analysis = report["date_analysis"]
            if analysis[f"{key}_count"]:
                report["issues"].append(
                    {
                        "issue": kind,
                        "column": str(series.name),
                        "count": analysis[f"{key}_count"],
                        "examples": analysis[f"{key}_examples"],
                    }
                )
    return report


def profile_dataframe(df):
    columns = [profile_column(df[c]) for c in df.columns]
    for target in columns:
        if not target.get("imputation"):
            continue
        suggestions = []
        available = target["imputation"]["available_methods"]
        group_method = "group_median" if "group_median" in available else "group_mode"
        for candidate in columns:
            if candidate["column_name"] == target["column_name"]:
                continue
            if (
                group_method in available
                and candidate["detected_type"] in ("category", "text", "identifier")
                and 2 <= candidate["unique_count"] <= 50
                and candidate["total_rows"] - candidate["missing_count"]
                > candidate["unique_count"]
            ):
                suggestions.append(
                    {
                        "method": group_method,
                        "group_by": [candidate["column_name"]],
                        "explanation": f"{candidate['column_name']} has repeated labels. If these identify related entities, consider {group_method.replace('_', ' ')}; repeated labels alone do not establish comparable groups.",
                    }
                )
            if (
                "forward_fill" in available
                and candidate["detected_type"]
                in ("date", "datetime", "integer", "decimal")
                and re.search(
                    r"time|date|sequence|order", candidate["column_name"], re.IGNORECASE
                )
            ):
                suggested = (
                    "linear_interpolation"
                    if "linear_interpolation" in available
                    else "forward_fill"
                )
                suggestions.append(
                    {
                        "method": suggested,
                        "order_by": candidate["column_name"],
                        "explanation": f"If {candidate['column_name']} describes a valid time/measurement sequence, consider {suggested.replace('_', ' ')}. Confirm entities and validate unique ordering first; this is not evidence of random missingness.",
                    }
                )
        target["imputation"]["contextual_recommendations"] = suggestions[:5]
    duplicates = detect_duplicates(df)
    missing_sets = {}
    masks = {c: df[c].map(missing).to_numpy() for c in df.columns}
    for row in range(len(df)):
        pattern = tuple(str(c) for c in df.columns if masks[c][row])
        if pattern:
            missing_sets[pattern] = missing_sets.get(pattern, 0) + 1
    patterns = sorted(missing_sets.items(), key=lambda pair: -pair[1])[:20]
    return {
        "missing_patterns": [
            {"columns": list(pattern), "rows": count} for pattern, count in patterns
        ],
        "rows": len(df),
        "columns_count": len(df.columns),
        "missing_count": sum(c["missing_count"] for c in columns),
        "duplicate_rows": duplicates,
        "issue_count": sum(len(c["issues"]) for c in columns) + bool(duplicates),
        "columns": columns,
    }

from .common import missing, scalar
from .date_analyzer import analyze_date_column
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
    duplicates = detect_duplicates(df)
    return {
        "rows": len(df),
        "columns_count": len(df.columns),
        "missing_count": sum(c["missing_count"] for c in columns),
        "duplicate_rows": duplicates,
        "issue_count": sum(len(c["issues"]) for c in columns) + bool(duplicates),
        "columns": columns,
    }

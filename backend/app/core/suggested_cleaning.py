"""Small, reviewable groups of conventional corrections; never an approval."""
from .workflow import manual_acceptances


GROUPS = {
    "whitespace": ("Trim extra whitespace", "Trim edges and collapse repeated internal whitespace. Text is retained.", "safe"),
    "boolean": ("Unify boolean labels", "Use true / false for recognized boolean answers. Other values are preserved.", "review"),
    "date_format": ("Standardize unambiguous dates", "Use YYYY-MM-DD, retaining timestamp time where present. Ambiguous and invalid input stays unchanged.", "review"),
    "time": ("Standardize clock times", "Use 24-hour HH:MM:SS for recognized clock times.", "review"),
    "duration": ("Standardize durations", "Use HH:MM:SS for recognized durations without wrapping hours over 24.", "review"),
    "capitalization": ("Standardize text capitalization", "Choose the intended case for all eligible text columns. Review acronyms and proper names.", "review"),
    "duplicate": ("Remove full duplicate rows", "Keep the first occurrence and remove only complete duplicate rows. This removes rows.", "destructive"),
}
ISSUES = {"extra_whitespace": "whitespace", "boolean_inconsistency": "boolean", "date_format_inconsistency": "date_format", "time_format": "time", "duration_format": "duration", "case_inconsistency": "capitalization"}


def suggested_cleaning(record):
    df = record["editor_df"]
    result = {"revision": record["editor_revision"], "groups": [], "deferred": [], "source_columns": list(df.columns), "protected_columns": sorted({item["column"] for item in manual_acceptances(record)})}
    if df.empty:
        return result
    protected = {item["column"] for item in manual_acceptances(record)}
    grouped = {}
    total = 0
    for column in record["editor_profile"]["columns"]:
        name = column["column_name"]
        reason = "User-entered corrections are preserved." if name in protected else "Identifiers are protected." if column["detected_type"] == "identifier" or record.get("column_rules", {}).get(name, {}).get("type") == "identifier" else "Choose whether possible missing-value labels should become empty first." if column.get("missing_marker_review", {}).get("count") else ""
        for issue in column["issues"]:
            kind = ISSUES.get(issue["issue"])
            if kind == "capitalization" and column["detected_type"] not in ("text", "category", "categorical"):
                kind = None
            if reason or not kind or total >= 99:
                if issue["count"]:
                    result["deferred"].append({"kind": issue["issue"], "label": f"{name}: {issue['issue'].replace('_', ' ')}", "count": issue["count"], "reason": reason or "This review is limited to 100 actions; run it again after these corrections." if total >= 99 else reason or "Your input is needed; use guided cleaning or column settings."})
                continue
            action, parameters = {
                "whitespace": ("trim_whitespace", {}),
                "boolean": ("normalize_boolean", {"format": "true_false"}),
                "date_format": ("normalize_dates", {"interpretation": "preserve", "output_format": "YYYY-MM-DD", "include_time": column["detected_type"] == "datetime"}),
                "time": ("normalize_time", {"format": "24_hour"}),
                "duration": ("normalize_duration", {}),
                "capitalization": ("normalize_capitalization", {"strategy": "title"}),
            }[kind]
            group = grouped.setdefault(kind, {"id": kind, "label": GROUPS[kind][0], "description": GROUPS[kind][1], "safety": GROUPS[kind][2], "steps": [], "columns": [], "count": 0})
            group["steps"].append({"kind": "fix", "body": {"revision": record["editor_revision"], "column": name, "row_index": int(df.index[0]), "scope": "column", "action": action, "parameters": parameters}})
            group["columns"].append(name)
            group["count"] += issue["count"]
            total += 1
    for kind in GROUPS:
        if kind in grouped:
            result["groups"].append(grouped[kind])
    duplicates = record["editor_profile"].get("duplicate_rows", 0)
    if duplicates:
        result["groups"].append({"id": "duplicate", "label": GROUPS["duplicate"][0], "description": GROUPS["duplicate"][1], "safety": "destructive", "columns": list(df.columns), "count": duplicates, "steps": [{"kind": "fix", "body": {"revision": record["editor_revision"], "column": str(df.columns[0]), "row_index": int(df.index[0]), "scope": "column", "action": "remove_duplicates", "parameters": {}}}]})
    return result

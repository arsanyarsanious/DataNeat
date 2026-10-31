"""Read-only whole-file navigation and comparison with the original upload."""
from .common import scalar


def find_value(df, query, column="", after=-1):
    if column and column not in df.columns:
        raise ValueError("Choose an existing column")
    columns = [column] if column else list(df.columns)
    needle = query.casefold()
    total = 0
    target = None
    for position, (index, row) in enumerate(df[columns].iterrows()):
        matches = [name for name in columns if needle in str(scalar(row[name]) if scalar(row[name]) is not None else "").casefold()]
        if matches:
            total += 1
            if target is None and position > after:
                target = {"row_index": int(index), "position": position, "page": position // 25 + 1, "column": str(matches[0])}
    return {"total_rows": total, "target": target}


def compare_original(record, page=1):
    original, current = record["df"], record["editor_df"]
    names = {name: name for name in original.columns}
    for change in record.get("editor_changes", []):
        if change.get("action") == "rename_column":
            old, new = change["column"], change["parameters"]["name"]
            names = {source: new if name == old else name for source, name in names.items()}
    rows, total = [], 0
    start, end = (page - 1) * 50, page * 50
    removed = ~original.index.isin(current.index)
    for source, name in names.items():
        before_values = original[source].map(scalar)
        after_values = current[name].reindex(original.index).map(scalar)
        equal = (before_values.eq(after_values) | (before_values.isna() & after_values.isna()))
        same_type = original[source].map(lambda v: type(scalar(v))).eq(current[name].map(lambda v: type(scalar(v))).reindex(original.index))
        indices = original.index[removed | ~(equal & same_type)]
        count = len(indices)
        for index in indices[max(0, start-total):max(0, end-total)]:
            is_removed = index not in current.index
            rows.append({"row_index": int(index), "column": name, "before": scalar(original.at[index, source]), "after": None if is_removed else scalar(current.at[index, name]), "removed_row": is_removed})
        total += count
    return {"total": total, "page": page, "rows": rows, "renamed_columns": [{"before": a, "after": b} for a, b in names.items() if a != b], "revision": record["editor_revision"]}

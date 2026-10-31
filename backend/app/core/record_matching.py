"""Bounded record similarity review and explicitly reviewed two-row merges.

Sorted-neighborhood indexes are a candidate search, not an exhaustive identity
test. The response reports both the comparison budget and missed coverage. No
suggestion is applied automatically and a similarity is never a probability.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from .common import scalar


MAX_COMPARISONS = 20_000
MAX_RESULTS = 100
NEIGHBOR_WINDOW = 2
MAX_TEXT_LENGTH = 1_000
_EXACT_NAME = re.compile(r"(?:^|[_\s-])(?:id|identifier|code|email|e-mail|phone|telephone|mobile|account|iban|postcode|postal|zip)(?:$|[_\s-])", re.I)
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)?|\d*\.\d+)(?:e[+-]?\d+)?$", re.I)


def validate_settings(settings: dict) -> dict:
    if not isinstance(settings, dict):
        raise ValueError("Record matching settings must be an object")
    action = settings.get("action", "review")
    if not isinstance(action, str) or action not in {"review", "merge", "keep_both"}:
        raise ValueError("Choose review, merge, or keep_both")
    columns = settings.get("columns", [])
    if not isinstance(columns, list) or not 2 <= len(columns) <= 5 or any(not isinstance(c, str) or not c for c in columns) or len(set(columns)) != len(columns):
        raise ValueError("Select two to five different matching columns")
    threshold = settings.get("threshold", 0.85)
    if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Similarity threshold must be between 0 and 1")
    block_by = settings.get("block_by") or ""
    if not isinstance(block_by, str):
        raise ValueError("Exact blocking column must be a column name")
    result = {"action": action, "columns": list(columns), "threshold": float(threshold), "block_by": block_by}
    if action != "review":
        for key in ("left_row", "right_row"):
            value = settings.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("Select two existing original spreadsheet rows")
            result[key] = value
        if result["left_row"] == result["right_row"]:
            raise ValueError("Select two different records")
    if action == "merge":
        keep_row = settings.get("keep_row")
        if isinstance(keep_row, bool) or not isinstance(keep_row, int) or keep_row not in (result["left_row"], result["right_row"]):
            raise ValueError("Choose which of the two original rows to retain")
        choices = settings.get("choices", {})
        if not isinstance(choices, dict) or any(not isinstance(k, str) or v not in ("left", "right") for k, v in choices.items()):
            raise ValueError("Choose the left or right value for each conflicting field")
        if settings.get("confirmed") is not True:
            raise ValueError("Review all field choices and confirm this merge")
        result.update(keep_row=int(keep_row), choices=dict(choices), confirmed=True)
    return result


def _empty(value: Any) -> bool:
    # Literal NA/null labels stay written until the separate marker review.
    if isinstance(value, str):
        return not value.strip()
    try:
        return value is None or bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value)).strip()).casefold()


def _exact_field(column: str, left: str, right: str) -> bool:
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", column)
    def number_like(value):
        return bool(_NUMBER.fullmatch(value) or re.fullmatch(r"[\d\s.,+%()$€£¥-]+", value) and any(char.isdigit() for char in value))
    return bool(_EXACT_NAME.search(name) or "@" in left or "@" in right or number_like(left) or number_like(right))


def _similarity(column: str, left: Any, right: Any) -> float | None:
    if _empty(left) and _empty(right):
        return None
    if _empty(left) or _empty(right):
        return 0.0
    one, two = _text(left), _text(right)
    if one == two:
        return 1.0
    if _exact_field(column, one, two):
        return 0.0
    # Long text is never silently truncated and compared as though complete.
    if len(one) > MAX_TEXT_LENGTH or len(two) > MAX_TEXT_LENGTH:
        return 0.0
    return SequenceMatcher(None, one, two, autojunk=False).ratio()


def _same(left: Any, right: Any) -> bool:
    if _empty(left) and _empty(right):
        return True
    return type(left).__name__ == type(right).__name__ and str(left) == str(right)


def _fingerprint(df: pd.DataFrame, row: int) -> str:
    values = [(str(column), type(df.at[row, column]).__name__, scalar(df.at[row, column])) for column in df.columns]
    encoded = json.dumps(values, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _kept_pairs(record: dict, df: pd.DataFrame) -> set[tuple[int, int]]:
    result = set()
    cache = {}
    for pair in record.get("kept_record_pairs", []):
        if not isinstance(pair, dict):
            continue
        left, right = pair.get("left_row"), pair.get("right_row")
        if left not in df.index or right not in df.index:
            continue
        for row in (left, right):
            if row not in cache:
                cache[row] = _fingerprint(df, row)
        if cache[left] == pair.get("left_fingerprint") and cache[right] == pair.get("right_fingerprint"):
            result.add(tuple(sorted((int(left), int(right)))))
    return result


def _frame(record: dict, settings: dict) -> pd.DataFrame:
    df = record.get("editor_df")
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Open a spreadsheet before reviewing records")
    required = set(settings["columns"]) | ({settings["block_by"]} if settings["block_by"] else set())
    unknown = required - set(df.columns)
    if unknown:
        raise ValueError("Unknown matching columns: " + ", ".join(sorted(unknown)))
    if not df.index.is_unique:
        raise ValueError("Record matching requires unique original row identifiers")
    return df


def _candidate_pairs(df: pd.DataFrame, columns: list[str], block_by: str, check) -> tuple[list[tuple[int, int]], dict]:
    """Keep a deterministic bounded sample from all sorted neighborhoods.

    Iteration is O(fields * rows * window), storage O(rows + budget), and
    expensive fuzzy comparison is capped. Sampling spans the complete table
    instead of silently inspecting only its first page or first rows.
    """
    blocks: dict[tuple[str, str], list[int]] = {}
    excluded = 0
    for position, row in enumerate(df.index):
        if position % 512 == 0:
            check()
        if block_by and _empty(df.at[row, block_by]):
            excluded += 1
            continue
        value = df.at[row, block_by] if block_by else ""
        key = (type(value).__name__, str(value))
        blocks.setdefault(key, []).append(int(row))
    selected: set[tuple[int, int]] = set()
    heap: list[tuple[int, tuple[int, int]]] = []
    positions = 0
    sampled_out = False
    for column in columns:
        check()
        for rows in blocks.values():
            ordered = sorted((_text(df.at[row, column]), row) for row in rows if not _empty(df.at[row, column]))
            for position, (_, left) in enumerate(ordered):
                if position % 512 == 0:
                    check()
                for offset in range(1, NEIGHBOR_WINDOW + 1):
                    if position + offset >= len(ordered):
                        break
                    right = ordered[position + offset][1]
                    pair = (min(left, right), max(left, right))
                    positions += 1
                    if pair in selected:
                        continue
                    rank = int.from_bytes(hashlib.blake2b(f"{pair[0]}:{pair[1]}".encode("ascii"), digest_size=8).digest(), "big")
                    if len(heap) < MAX_COMPARISONS:
                        selected.add(pair)
                        heapq.heappush(heap, (-rank, pair))
                    elif rank < -heap[0][0]:
                        sampled_out = True
                        _, previous = heapq.heapreplace(heap, (-rank, pair))
                        selected.remove(previous)
                        selected.add(pair)
                    else:
                        sampled_out = True
    return sorted(selected), {"candidate_positions": positions, "sampled_candidates": sampled_out, "rows_without_block_value": excluded, "searched_rows": len(df) - excluded, "block_count": len(blocks)}


def _pair_details(df: pd.DataFrame, left: int, right: int, columns: list[str]) -> dict | None:
    fields = []
    scores = []
    shared_values = 0
    positive_fields = 0
    for column in columns:
        one, two = df.at[left, column], df.at[right, column]
        similarity = _similarity(column, one, two)
        fields.append({"column": column, "left": scalar(one), "right": scalar(two), "similarity": None if similarity is None else round(similarity, 4), "comparison": "exact" if _exact_field(column, _text(one), _text(two)) else "text"})
        if similarity is not None:
            scores.append(similarity)
        if not _empty(one) and not _empty(two):
            shared_values += 1
            if similarity and similarity > 0:
                positive_fields += 1
    if shared_values < 2 or positive_fields < 2 or not scores:
        return None
    return {
        "left_row": int(left), "right_row": int(right), "score": round(sum(scores) / len(scores), 4),
        "fields": fields,
    }


def review(record: dict, settings: dict, check=lambda: None) -> dict:
    config = validate_settings({**settings, "action": "review"})
    df = _frame(record, config)
    candidates, coverage = _candidate_pairs(df, config["columns"], config["block_by"], check)
    kept = _kept_pairs(record, df)
    pairs = []
    matched = compared = skipped_kept = long_text_rows = 0
    for position, (left, right) in enumerate(candidates):
        if position % 64 == 0:
            check()
        if (left, right) in kept:
            skipped_kept += 1
            continue
        compared += 1
        details = _pair_details(df, left, right, config["columns"])
        if details and details["score"] >= config["threshold"]:
            matched += 1
            details.update(
                left_values={str(c): scalar(df.at[left, c]) for c in df.columns},
                right_values={str(c): scalar(df.at[right, c]) for c in df.columns},
                conflicts=[str(c) for c in df.columns if not _empty(df.at[left, c]) and not _empty(df.at[right, c]) and not _same(df.at[left, c], df.at[right, c])],
            )
            pairs.append(details)
            # Bound full-row payload memory as well as candidate comparisons.
            if len(pairs) > MAX_RESULTS:
                pairs.sort(key=lambda item: (-item["score"], item["left_row"], item["right_row"]))
                pairs.pop()
    for column in config["columns"]:
        check()
        long_text_rows += int(df[column].map(lambda value: not _empty(value) and len(_text(value)) > MAX_TEXT_LENGTH).sum())
    pairs.sort(key=lambda item: (-item["score"], item["left_row"], item["right_row"]))
    warnings = ["Similarity scores compare the selected values; they are not probabilities that two people or records are the same.", "Sorted-neighborhood search checks nearby values, not every possible row pair. No suggested records are merged automatically."]
    if coverage["sampled_candidates"]:
        warnings.append(f"The search exceeded its {MAX_COMPARISONS:,}-pair comparison budget. A deterministic sample spanning the table was reviewed; other matches may exist. Narrow the search with an exact blocking column.")
    if matched > MAX_RESULTS:
        warnings.append(f"Showing the {MAX_RESULTS} highest-scoring pairs from {matched} matches found in the compared candidates. Narrow the selected columns or blocking group to review more.")
    if coverage["rows_without_block_value"]:
        warnings.append(f"{coverage['rows_without_block_value']:,} rows were excluded because their exact blocking value is empty.")
    if long_text_rows:
        warnings.append(f"{long_text_rows:,} selected cells exceed {MAX_TEXT_LENGTH:,} characters; unequal long values are compared as different, without text truncation.")
    return {
        "pairs": pairs, "columns": config["columns"], "threshold": config["threshold"], "block_by": config["block_by"],
        "row_count": len(df), "compared_pairs": compared, "matched_pairs": matched, "returned_pairs": len(pairs),
        "kept_pairs_skipped": skipped_kept, "candidate_limit": MAX_COMPARISONS, "result_limit": MAX_RESULTS,
        "search_method": "sorted_neighborhood", "neighborhood_window": NEIGHBOR_WINDOW,
        "exhaustive": False, "truncated": coverage["sampled_candidates"] or matched > MAX_RESULTS,
        "coverage": coverage, "warnings": warnings,
    }


def apply(record: dict, settings: dict, check=lambda: None) -> tuple[pd.DataFrame, dict]:
    config = validate_settings(settings)
    df = _frame(record, config)
    if config["action"] == "review":
        return df.copy(deep=True), {"action": "review_records", "review": review(record, config, check), "changed_cells": 0, "affected_rows": 0}
    left, right = config["left_row"], config["right_row"]
    if left not in df.index or right not in df.index:
        raise ValueError("One of these original rows no longer exists. Refresh the record review")
    if config["block_by"] and (not _same(df.at[left, config["block_by"]], df.at[right, config["block_by"]]) or _empty(df.at[left, config["block_by"]])):
        raise ValueError("These records do not share the selected exact blocking value")
    check()
    pair = {"left_row": left, "right_row": right, "left_fingerprint": _fingerprint(df, left), "right_fingerprint": _fingerprint(df, right)}
    if config["action"] == "keep_both":
        previous = [item for item in record.get("kept_record_pairs", []) if not isinstance(item, dict) or {item.get("left_row"), item.get("right_row")} != {left, right}]
        # User decisions stay valid only while both complete row contents agree.
        record["kept_record_pairs"] = previous + [pair]
        return df.copy(deep=True), {"action": "keep_records", "reviewed_pair": pair, "changed_cells": 0, "affected_rows": 0}
    unknown = set(config["choices"]) - set(df.columns)
    if unknown:
        raise ValueError("Unknown merge fields: " + ", ".join(sorted(unknown)))
    conflicts = [str(column) for column in df.columns if not _empty(df.at[left, column]) and not _empty(df.at[right, column]) and not _same(df.at[left, column], df.at[right, column])]
    unresolved = set(conflicts) - set(config["choices"])
    if unresolved:
        raise ValueError("Choose which value to retain for every conflicting field: " + ", ".join(sorted(unresolved)))
    survivor = config["keep_row"]
    removed = right if survivor == left else left
    chosen = {}
    source_rows = {}
    for column in df.columns:
        check()
        one, two = df.at[left, column], df.at[right, column]
        if column in conflicts:
            source_rows[column] = left if config["choices"][column] == "left" else right
        elif _empty(one) and not _empty(two):
            source_rows[column] = right
        elif _empty(two) and not _empty(one):
            source_rows[column] = left
        else:
            source_rows[column] = survivor
        chosen[column] = df.at[source_rows[column], column]
    result = df.copy(deep=True).astype(object)
    changed = 0
    for column, value in chosen.items():
        if not _same(df.at[survivor, column], value):
            changed += 1
        result.at[survivor, column] = value
    result = result.drop(index=removed)
    return result, {"action": "merge_records", "retained_row": survivor, "removed_row": removed, "changed_cells": changed, "affected_rows": 2, "reviewed_pair": pair, "conflict_choices": {c: config["choices"][c] for c in conflicts}, "source_rows": source_rows}

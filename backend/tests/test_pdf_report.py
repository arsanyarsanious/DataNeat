from app.core.pdf_report import cleaning_pdf


def test_pdf_report_handles_empty_history_and_escaped_values():
    profile = {"rows": 3, "columns_count": 1, "missing_count": 1, "duplicate_rows": 0, "issue_count": 0, "columns": []}
    pdf = cleaning_pdf("sample <test>.csv", [{"action": "replace", "column": "A & B", "scope": "cell", "row_index": 0, "changed_cells": 1, "examples": [{"row_index": 0, "before": "<bad>", "after": "fixed & safe"}]}], profile, profile)
    assert pdf.read().startswith(b"%PDF-")
    assert cleaning_pdf("empty.csv", [], profile, profile).read().startswith(b"%PDF-")

"""Local/Office add-in analysis endpoint.

This is intentionally read-only: it profiles an uploaded sheet snapshot and
returns compact per-cell issue markers for Excel highlighting. Corrections stay
in the add-in's later phases; no workbook mutation happens here.
"""
import os

from fastapi import File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from ..core.file_parser import parse_file
from ..core.interactive import annotate
from ..core.profiler import profile_dataframe

ADDIN_MAX_UPLOAD = int(os.getenv("ADDIN_MAX_UPLOAD_MB", "60")) * 1024 * 1024
ADDIN_MAX_CELLS = max(0, int(os.getenv("ADDIN_MAX_CELLS", "3000000") or "0"))
ADDIN_HIGHLIGHT_CAP = max(1, int(os.getenv("ADDIN_HIGHLIGHT_CAP", "50000") or "50000"))
ANNOTATION_CHUNK_ROWS = max(1000, int(os.getenv("ADDIN_ANNOTATION_ROWS", "20000") or "20000"))


def install_addin(app):
    @app.post("/api/addin/analyze")
    async def addin_analyze(
        file: UploadFile = File(...),
        highlight_cap: int = Form(ADDIN_HIGHLIGHT_CAP),
    ):
        data = bytearray()
        while chunk := await file.read(1024 * 1024):
            data.extend(chunk)
            if len(data) > ADDIN_MAX_UPLOAD:
                raise HTTPException(413, "Workbook snapshot is above this add-in build's limit")
        await file.close()
        if not data:
            raise HTTPException(422, "The selected sheet is empty")

        try:
            df, metadata = await run_in_threadpool(parse_file, bytes(data), "excel-sheet.csv")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        cells_count = len(df) * max(1, len(df.columns))
        if ADDIN_MAX_CELLS and cells_count > ADDIN_MAX_CELLS:
            raise HTTPException(
                413,
                f"This sheet has {cells_count:,} cells; this add-in build supports "
                f"up to {ADDIN_MAX_CELLS:,}. Select a smaller range or split the sheet.",
            )

        report = await run_in_threadpool(profile_dataframe, df)

        def collect_chunk(start: int, part):
            annotations = annotate(df, report, part)
            found = []
            for offset, row in enumerate(annotations):
                for column_index, issues in enumerate(row):
                    if issues:
                        found.append(
                            {
                                "row": start + offset,
                                "column": column_index,
                                "kinds": sorted({issue["kind"] for issue in issues}),
                            }
                        )
            return found

        cap = max(1, min(int(highlight_cap or ADDIN_HIGHLIGHT_CAP), 200000))
        cells = []
        total_issue_cells = 0
        truncated = False
        for start in range(0, len(df), ANNOTATION_CHUNK_ROWS):
            part = df.iloc[start : start + ANNOTATION_CHUNK_ROWS]
            found = await run_in_threadpool(collect_chunk, start, part)
            total_issue_cells += len(found)
            remaining = cap - len(cells)
            if remaining > 0:
                cells.extend(found[:remaining])
            if len(cells) >= cap and len(found) > max(0, remaining):
                truncated = True

        return {
            "filename": "excel-sheet.csv",
            "rows": len(df),
            "columns_count": len(df.columns),
            "cells_count": cells_count,
            "columns": [
                {
                    "name": str(column["column_name"]),
                    "detected_type": column["detected_type"],
                    "missing_count": column["missing_count"],
                    "issues": [
                        {"kind": item["issue"], "count": item["count"]}
                        for item in column["issues"]
                    ],
                }
                for column in report["columns"]
            ],
            "metadata": metadata,
            "cells": cells,
            "total_issue_cells": total_issue_cells,
            "highlight_cap": cap,
            "truncated": truncated,
        }

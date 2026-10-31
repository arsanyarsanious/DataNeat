import csv
import os
import io
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pandas as pd
from charset_normalizer import from_bytes
from openpyxl import load_workbook

MAX_ROWS = max(1, min(100000, int(os.getenv("MAX_UPLOAD_ROWS", "100000"))))
MAX_COLUMNS = max(1, min(200, int(os.getenv("MAX_UPLOAD_COLUMNS", "200"))))
MAX_INSPECT_SHEETS = 1000
MAX_WORKBOOK_EXPANDED_BYTES = 100 * 1024 * 1024


def _formula_result_metadata(archive, selected):
    """Validate saved formula results without evaluating spreadsheet expressions."""
    main_ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    sheet = next((item for item in workbook_xml.iter(f"{main_ns}sheet") if item.get("name") == selected), None)
    relation_id = sheet.get(f"{rel_ns}id") if sheet is not None else None
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relation = next((item for item in relationships if item.get("Id") == relation_id), None)
    if relation is None or relation.get("TargetMode") == "External":
        raise ValueError("Invalid XLSX worksheet reference")
    target = relation.get("Target", "")
    sheet_path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target))
    formula_count = missing_count = error_count = 0
    missing_examples = []
    # Iterate rows so even a large selected sheet does not build an XML cell tree.
    with archive.open(sheet_path) as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag == f"{main_ns}c":
                if element.find(f"{main_ns}f") is not None:
                    formula_count += 1
                    value = element.find(f"{main_ns}v")
                    # An explicit saved string result may be legitimately empty.
                    saved = value is not None and (value.text not in (None, "") or element.get("t") == "str")
                    if not saved:
                        missing_count += 1
                        if len(missing_examples) < 8:
                            missing_examples.append(element.get("r", "unknown cell"))
                    elif element.get("t") == "e":
                        error_count += 1
                element.clear()
            elif element.tag == f"{main_ns}row":
                element.clear()
    if missing_count:
        locations = ", ".join(missing_examples)
        if missing_count > len(missing_examples):
            locations += f" and {missing_count - len(missing_examples):,} more"
        raise ValueError(
            f"Worksheet '{selected}' has {missing_count:,} formula cells without saved results ({locations}). "
            "Open the workbook in Excel, recalculate the formulas, save it, and upload it again. "
            "DataNeat imports saved results and does not calculate formulas."
        )
    return {"formula_cells": formula_count, "formula_error_cells": error_count,
            "formula_notice": "Formula cells use their last saved Excel results. DataNeat does not recalculate formulas; changing input values here will not update those results." if formula_count else None}


def inspect_workbook(data, filename):
    """List bounded worksheet metadata without profiling or storing workbook data.

    Counts use the worksheet's reported dimensions, with the first row treated
    as a header, just as the normal import does. Do not force a dimensions scan:
    it could read every cell before the user has chosen a worksheet.
    """
    if Path(filename).suffix.lower() != ".xlsx":
        raise ValueError("Choose an XLSX workbook to inspect its worksheets")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_WORKBOOK_EXPANDED_BYTES:
                raise ValueError("Workbook expands beyond the safety limit")
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except (zipfile.BadZipFile, KeyError):
        raise ValueError("Invalid XLSX workbook")
    try:
        names = workbook.sheetnames
        if not names:
            raise ValueError("Workbook has no worksheets")
        if len(names) > MAX_INSPECT_SHEETS:
            raise ValueError(f"Choose a workbook with no more than {MAX_INSPECT_SHEETS:,} tabs")
        sheets = []
        for name in names:
            worksheet = workbook[name]
            max_row = getattr(worksheet, "max_row", None)
            max_column = getattr(worksheet, "max_column", None)
            rows = max(0, int(max_row or 0) - 1)
            columns = max(0, int(max_column or 0))
            reason = None
            if not hasattr(worksheet, "iter_rows"):
                reason = "This tab is a chart, not a worksheet with tabular data."
            elif max_row is None or max_column is None:
                reason = "Worksheet dimensions are unavailable. Resave the workbook in Excel and upload it again."
            elif not rows or not columns:
                reason = "No data rows. Choose a worksheet with a header and at least one data row."
            elif rows > MAX_ROWS or columns > MAX_COLUMNS:
                reason = f"This worksheet exceeds the limit of {MAX_ROWS:,} data rows or {MAX_COLUMNS} columns."
            sheets.append({"name": name, "rows": rows, "columns": columns,
                           "hidden": getattr(worksheet, "sheet_state", "visible") != "visible",
                           "selectable": reason is None, **({"reason": reason} if reason else {})})
        return {"filename": Path(filename).name, "sheets": sheets,
                "limits": {"max_rows": MAX_ROWS, "max_columns": MAX_COLUMNS, "max_sheets": MAX_INSPECT_SHEETS},
                "selected_sheet": None}
    finally:
        workbook.close()


def unique_headers(headers):
    seen, output = set(), []
    for index, value in enumerate(headers):
        base = str(value) if value not in (None, "") else f"Column_{index + 1}"
        name, suffix = base, 2
        while name in seen:
            name = f"{base}_{suffix}"
            suffix += 1
        seen.add(name)
        output.append(name)
    return output


def parse_file(data, filename, sheet=None):
    extension = Path(filename).suffix.lower()
    sheets = []
    if extension == ".csv":
        best = from_bytes(data).best()
        if not best:
            raise ValueError("Cannot detect CSV encoding")
        text = str(best)
        if "\x00" in text:
            raise ValueError("Invalid CSV contents")
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
        reader = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError("The file is empty")
        if not headers or len(headers) > MAX_COLUMNS:
            raise ValueError(f"File must have 1–{MAX_COLUMNS} columns")
        rows = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(headers):
                raise ValueError("CSV rows have inconsistent field counts")
            rows.append(row)
            if len(rows) > MAX_ROWS:
                raise ValueError(f"Maximum {MAX_ROWS:,} rows supported")
        metadata = {"encoding": best.encoding, "delimiter": delimiter}
    elif extension == ".xlsx":
        workbook = None
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(i.file_size for i in archive.infolist()) > MAX_WORKBOOK_EXPANDED_BYTES:
                    raise ValueError("Workbook expands beyond the safety limit")
                workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
                sheets = workbook.sheetnames
                if sheet and sheet not in sheets:
                    raise ValueError("Unknown worksheet")
                selected = sheet or sheets[0]
                worksheet = workbook[selected]
                if worksheet.max_row > MAX_ROWS + 1 or worksheet.max_column > MAX_COLUMNS:
                    raise ValueError("Workbook dimensions exceed limits")
                formula_metadata = _formula_result_metadata(archive, selected)
            iterator = worksheet.iter_rows()

            def cell_value(cell):
                value = cell.value
                if (
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and re.fullmatch(r"0{2,}", cell.number_format or "")
                ):
                    return str(value).zfill(len(cell.number_format))
                return value

            headers = [cell_value(cell) for cell in next(iterator, [])]
            rows = []
            for row in iterator:
                rows.append([cell_value(cell) for cell in row])
                if len(rows) > MAX_ROWS:
                    raise ValueError(f"Maximum {MAX_ROWS:,} rows supported")
            metadata = {"worksheet": selected, **formula_metadata, "compatibility_warning": "Only the selected worksheet's data table is cleaned. Export does not preserve workbook formatting, charts, macros, merged cells, other worksheets or executable formulas. Formula cells are imported as their last saved results and exported as values, without recalculation. Excel numeric values may already have lost precision; store long identifiers as text."}
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
            raise ValueError("Invalid XLSX workbook")
        finally:
            if workbook is not None:
                workbook.close()
    else:
        raise ValueError("Only CSV and XLSX files are supported")
    if not headers or len(headers) > MAX_COLUMNS:
        raise ValueError(f"File must have 1–{MAX_COLUMNS} columns")
    if not rows:
        raise ValueError("File has no data rows")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"Maximum {MAX_ROWS:,} rows supported")
    names = unique_headers(headers)
    return pd.DataFrame(rows, columns=names, dtype=object), {
        "sheets": sheets,
        "header_adjustments": [
            {"original": str(a), "name": b}
            for a, b in zip(headers, names)
            if str(a) != b
        ],
        **metadata,
    }

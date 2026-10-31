"""Optional, bounded original-cell fill presentation; never changes working data.

Only source fill colors are cached. Worksheet data/formulas are not evaluated or
returned here, and ownership is checked by the calling file endpoint first.
"""
from array import array
from collections import OrderedDict
import colorsys
import hashlib
import io
from numbers import Integral
import posixpath
import re
import sys
import threading
import xml.etree.ElementTree as ET
import zipfile

from openpyxl.styles.colors import COLOR_INDEX

from .file_parser import MAX_COLUMNS, MAX_ROWS, MAX_WORKBOOK_EXPANDED_BYTES

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_DRAW_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_HEX = re.compile(r"^(?:[A-Fa-f0-9]{6}|[A-Fa-f0-9]{8})$")
_CELL = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})$")
_CACHE_LIMIT = 64 * 1024 * 1024
_CACHE_ENTRIES = 8
_CACHE = OrderedDict()
_CACHE_BYTES = 0
_CACHE_GUARD = threading.RLock()
_INFLIGHT = {}
_LIMITATIONS = [
    "Shows original solid background fills only. Conditional formatting, patterns, gradients, fonts and borders are not reproduced.",
    "Colors stay at their original cell positions; merged records keep the retained row's formatting. New or unmapped columns have no original fill.",
    "Display only. Cleaned exports remain data tables; the original workbook is preserved separately.",
]


def _rgb(value):
    return "#" + value[-6:].upper() if isinstance(value, str) and _HEX.fullmatch(value) else None


def _part(target, base="xl"):
    if not isinstance(target, str) or not target or ":" in target or "\\" in target:
        raise ValueError("Unsupported workbook relationship")
    path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(base, target))
    if not path.startswith("xl/") or "/../" in path:
        raise ValueError("Unsupported workbook relationship")
    return path


def _parts(archive, worksheet):
    root = ET.fromstring(archive.read("xl/workbook.xml"))
    sheets = root.find(f"{{{_NS}}}sheets")
    selected = next((item for item in (sheets if sheets is not None else []) if item.get("name") == worksheet), None)
    if selected is None:
        raise ValueError("Original worksheet is unavailable")
    relation_id = selected.get(f"{{{_REL_NS}}}id")
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {}
    kinds = {}
    for item in relations:
        if item.get("TargetMode") == "External":
            continue
        target = _part(item.get("Target"))
        targets[item.get("Id")] = target
        kinds[item.get("Type", "").rsplit("/", 1)[-1]] = target
    if relation_id not in targets:
        raise ValueError("Original worksheet is unavailable")
    return targets[relation_id], kinds.get("styles", "xl/styles.xml"), kinds.get("theme", "xl/theme/theme1.xml")


def _theme(archive, path):
    if path not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(path))
    scheme = root.find(f".//{{{_DRAW_NS}}}clrScheme")
    if scheme is None:
        return []
    colors = {}
    for element in scheme:
        if not len(element):
            continue
        color = element[0]
        value = color.get("lastClr") if color.tag.rsplit("}", 1)[-1] == "sysClr" else color.get("val")
        colors[element.tag.rsplit("}", 1)[-1]] = _rgb(value)
    order = ("lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink")
    return [colors.get(name) for name in order]


def _color(element, theme, indexed):
    if element is None or element.get("auto") in ("1", "true"):
        return None
    value = _rgb(element.get("rgb"))
    try:
        if value is None and element.get("theme") is not None:
            index = int(element.get("theme"))
            value = theme[index] if 0 <= index < len(theme) else None
        if value is None and element.get("indexed") is not None:
            index = int(element.get("indexed"))
            value = _rgb(indexed[index]) if 0 <= index < min(len(indexed), 64) else None
        if value and element.get("tint") is not None:
            tint = float(element.get("tint"))
            if not -1 <= tint <= 1:
                return None
            red, green, blue = (int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))
            hue, light, saturation = colorsys.rgb_to_hls(red, green, blue)
            light = light * (1 + tint) if tint < 0 else light * (1 - tint) + tint
            components = colorsys.hls_to_rgb(hue, light, saturation)
            value = "#" + "".join(f"{max(0, min(255, round(component * 255))):02X}" for component in components)
    except (ValueError, IndexError, TypeError, OverflowError):
        return None
    return value


def _styles(archive, path, theme):
    if path not in archive.namelist():
        return [0], [None]
    root = ET.fromstring(archive.read(path))
    indexed = list(COLOR_INDEX)
    custom = root.find(f"{{{_NS}}}colors/{{{_NS}}}indexedColors")
    if custom is not None:
        indexed = [item.get("rgb") for item in custom]
    fills = []
    fill_elements = root.find(f"{{{_NS}}}fills")
    for item in fill_elements if fill_elements is not None else []:
        pattern = item.find(f"{{{_NS}}}patternFill")
        fills.append(_color(pattern.find(f"{{{_NS}}}fgColor"), theme, indexed) if pattern is not None and pattern.get("patternType") == "solid" else None)
    palette = [None]
    palette_ids = {None: 0}
    style_ids = []
    style_elements = root.find(f"{{{_NS}}}cellXfs")
    for item in style_elements if style_elements is not None else []:
        try:
            index = int(item.get("fillId", "0"))
            value = fills[index] if 0 <= index < len(fills) else None
        except ValueError:
            value = None
        if value not in palette_ids:
            if len(palette) >= 65536:
                raise ValueError("Too many original fill colors")
            palette_ids[value] = len(palette)
            palette.append(value)
        style_ids.append(palette_ids[value])
        if len(style_ids) > 65536:
            raise ValueError("Too many workbook cell styles")
    return style_ids or [0], palette


def _style_id(value, styles):
    try:
        index = int(value)
        return styles[index] if 0 <= index < len(styles) else 0
    except (ValueError, TypeError):
        return 0


def _extract(data, worksheet, rows, columns):
    """Scan XML once, keeping only bounded compact palette rows, never values."""
    if not 0 < columns <= MAX_COLUMNS or not 0 <= rows <= MAX_ROWS:
        raise ValueError("Original worksheet dimensions are unsupported")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(item.file_size for item in archive.infolist()) > MAX_WORKBOOK_EXPANDED_BYTES:
            raise ValueError("Workbook expands beyond the safety limit")
        path, style_path, theme_path = _parts(archive, worksheet)
        styles, palette = _styles(archive, style_path, _theme(archive, theme_path))
        defaults = array("H", [0] * columns)
        selected_rows = {}
        sheet_data = None
        conditional = False
        with archive.open(path) as stream:
            for event, element in ET.iterparse(stream, events=("start", "end")):
                name = element.tag.rsplit("}", 1)[-1]
                if event == "start":
                    if name == "sheetData":
                        sheet_data = element
                    elif name == "conditionalFormatting":
                        conditional = True
                    continue
                if name == "col":
                    try:
                        start, stop = int(element.get("min", "0")), int(element.get("max", "0"))
                    except ValueError:
                        continue
                    for index in range(max(1, start), min(columns, stop) + 1):
                        defaults[index - 1] = _style_id(element.get("style"), styles)
                    element.clear()
                elif name == "row":
                    try:
                        row = int(element.get("r", "0"))
                    except ValueError:
                        row = 0
                    if 2 <= row <= rows + 1:
                        values = array("H", defaults)
                        if element.get("s") is not None and element.get("customFormat") not in ("0", "false"):
                            values = array("H", [_style_id(element.get("s"), styles)] * columns)
                        for cell in element:
                            match = _CELL.fullmatch(cell.get("r", ""))
                            if not match or int(match[2]) != row:
                                continue
                            column = 0
                            for char in match[1]:
                                column = column * 26 + ord(char) - 64
                            if 1 <= column <= columns and cell.get("s") is not None:
                                values[column - 1] = _style_id(cell.get("s"), styles)
                        if values != defaults:
                            selected_rows[row - 2] = values.tobytes()
                    element.clear()
                    if sheet_data is not None:
                        sheet_data.clear()
                elif name in ("conditionalFormatting", "extLst"):
                    element.clear()
        default_bytes = defaults.tobytes()
        default_count = sum(bool(value) for value in defaults)
        colored = default_count * rows
        for values in selected_rows.values():
            decoded = array("H")
            decoded.frombytes(values)
            colored += sum(bool(value) for value in decoded) - default_count
        size = sys.getsizeof(selected_rows) + sum(sys.getsizeof(k) + sys.getsizeof(v) for k, v in selected_rows.items()) + sys.getsizeof(palette) + sum(sys.getsizeof(value) for value in palette) + sys.getsizeof(default_bytes)
        if size > _CACHE_LIMIT:
            raise ValueError("Original colors exceed the display memory limit")
        return {"rows": selected_rows, "defaults": default_bytes, "palette": tuple(palette), "has_colors": colored > 0, "conditional": conditional, "size": size}


def _cached(data, worksheet, rows, columns):
    global _CACHE_BYTES
    key = (hashlib.sha256(data).digest(), worksheet, rows, columns)
    with _CACHE_GUARD:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        pending = _INFLIGHT.setdefault(key, threading.Lock())
    try:
        with pending:
            with _CACHE_GUARD:
                if key in _CACHE:
                    _CACHE.move_to_end(key)
                    return _CACHE[key]
            value = _extract(data, worksheet, rows, columns)
            with _CACHE_GUARD:
                while _CACHE and (len(_CACHE) >= _CACHE_ENTRIES or _CACHE_BYTES + value["size"] > _CACHE_LIMIT):
                    _, discarded = _CACHE.popitem(last=False)
                    _CACHE_BYTES -= discarded["size"]
                _CACHE[key] = value
                _CACHE_BYTES += value["size"]
            return value
    finally:
        with _CACHE_GUARD:
            if _INFLIGHT.get(key) is pending:
                _INFLIGHT.pop(key, None)


def _column_sources(record, columns):
    original = list(record["df"].columns)
    mapping = {name: index for index, name in enumerate(original)}
    for change in record.get("editor_changes", []):
        if change.get("action") == "rename_column":
            old, new = change.get("column"), change.get("parameters", {}).get("name")
            if old in mapping and new:
                if new in mapping and new != old:
                    raise ValueError("Original column positions are unavailable")
                mapping[new] = mapping.pop(old)
    sources = [mapping.get(name) for name in columns]
    if columns and not any(source is not None for source in sources):
        raise ValueError("Original column positions are unavailable")
    return sources


def original_colors(record, preview, enabled=False):
    """Return presentation status; attach page-aligned fills only when requested."""
    supported = str(record.get("filename", "")).lower().endswith(".xlsx") and isinstance(record.get("original_bytes"), bytes)
    state = {"supported": supported, "status": "off" if supported else "unsupported", "message": "Original colors are hidden while cleaning." if supported else "Original colors are available for XLSX files only.", "limitations": list(_LIMITATIONS)}
    if not enabled or not supported:
        return state
    try:
        source = record["df"]
        indices = preview.get("row_indices")
        if indices is None:
            first = (preview["page"] - 1) * preview["page_size"]
            indices = list(source.iloc[first:first + len(preview["rows"])].index)
        if not source.index.is_unique or any(not isinstance(index, Integral) or index < 0 or index >= len(source) or index not in source.index for index in indices):
            raise ValueError("Original row positions are unavailable")
        columns = _column_sources(record, preview["columns"])
        colors = _cached(record["original_bytes"], record.get("metadata", {}).get("worksheet"), len(source), len(source.columns))
        matrix = []
        for index in indices:
            row = array("H")
            row.frombytes(colors["rows"].get(int(index), colors["defaults"]))
            matrix.append([colors["palette"][row[position]] if position is not None else None for position in columns])
        preview["original_fills"] = matrix
        state.update(status="ready", has_colors=colors["has_colors"], message="Original cell colors are shown. Issue markers identify cleaning findings." if colors["has_colors"] else "No original solid cell fills were found in this worksheet.")
        if colors["conditional"]:
            state["limitations"].insert(0, "This worksheet contains conditional formatting; its calculated colors are not reproduced.")
    except (ValueError, TypeError, KeyError, IndexError, OSError, ET.ParseError, zipfile.BadZipFile):
        state.update(status="unavailable", message="Original colors could not be safely read for this workbook. Cleaning remains available.")
    return state


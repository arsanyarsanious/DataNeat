"""Readable, paginated cleaning audit; no external service receives file data."""
import io
import json
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


def cleaning_pdf(filename, steps, before, after, preparation=None, revision=None):
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="AuditBody", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=6, wordWrap="CJK"))
    styles["Heading1"].textColor = colors.HexColor("#217346")
    story = []

    def text(value, style="AuditBody"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def add(value, style="AuditBody"):
        story.append(text(value, style))

    def name(value):
        return str(value).replace("_", " ").capitalize()

    add("DataNeat | Cleaning report", "Title")
    add(filename)
    add("Generated " + datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC"))
    if revision is not None:
        add(f"Interactive sheet revision: {revision}")
    add("Your original upload is preserved. This report describes the current cleaned copy. Undone steps are excluded.")
    add("Overview", "Heading1")
    rows = [[text("Measure"), text("Original"), text("Current copy")]]
    for label, key in [("Rows", "rows"), ("Columns", "columns_count"), ("Missing cells", "missing_count"), ("Duplicate rows", "duplicate_rows"), ("Issue categories", "issue_count")]:
        rows.append([text(label), text(before.get(key, "—")), text(after.get(key, "—"))])
    table = Table(rows, colWidths=[235, 115, 115], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf6f1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#e7ebef"))]))
    story.extend([table, Spacer(1, 12)])
    if preparation:
        add("Automatic preparation", "Heading1")
        for item in preparation:
            add(item)
    add("Cleaning steps, in execution order", "Heading1")
    if not steps:
        add("No user-confirmed cleaning steps have been applied.")
    for index, step in enumerate(steps, 1):
        action = step.get("action", step.get("operation", "Cleaning step"))
        count = step.get("changed_cells", step.get("modified_values", 0))
        heading = f"{index}. {name(action)}"
        scope = step.get("scope", "column" if step.get("column") else "dataset")
        story.append(KeepTogether([text(heading, "Heading2"), text(f"Column: {step.get('column') or 'Entire dataset'} | Scope: {scope} | Affected cells / rows: {count}")]))
        if scope == "cell" and "row_index" in step:
            add(f"Spreadsheet row: {step['row_index'] + 2}")
        if step.get("removed_rows"):
            add(f"Rows removed: {step['removed_rows']}. Merged field selections are recorded below.")
        parameters = step.get("parameters", {})
        for key, value in parameters.items():
            if key in ("confirmed", "replacements"):
                continue
            if isinstance(value, (str, int, float, bool, list)):
                add(f"{name(key)}: {', '.join(map(str, value)) if isinstance(value, list) else value}")
            elif isinstance(value, dict):
                add(f"{name(key)}: {json.dumps(value, ensure_ascii=False)}")
        if parameters.get("replacements"):
            add("Individual date corrections were supplied for specific rows.")
        estimate = step.get("imputation")
        if estimate:
            add(f"Imputed estimates: {estimate.get('imputed_count', 0)} | Missing before: {estimate.get('missing_before', 0)} | Missing after: {estimate.get('missing_after', 0)}")
            original = estimate.get("distribution_before", {}).get("numeric")
            current = estimate.get("distribution_after", {}).get("numeric")
            if original and current:
                for metric in ("mean", "median", "std"):
                    add(f"{name(metric)} before / after: {original.get(metric)} / {current.get(metric)}")
            validation = estimate.get("validation", {})
            if validation.get("status") == "available":
                add(f"Held-out test: {validation['held_out_count']} observed targets. Model mean absolute error: {validation['mae']}; training median baseline error: {validation['baseline_mae']}.")
            elif validation:
                add("Model validation unavailable: " + validation.get("reason", "Insufficient evidence"))
        examples = step.get("examples", [])
        if examples:
            add("Examples of changes (sample only):")
            for example in examples:
                old = example.get("before")
                new = example.get("after")
                add(f"Column {example.get('column', step.get('column', ''))}, row {example['row_index'] + 2}: {old if old is not None else '[empty]'} → {'[row removed]' if example.get('removed_row') else new if new is not None else '[empty]'}")
        for warning in step.get("warnings", []):
            add("Note: " + warning)
        story.append(Spacer(1, 8))
    add("Remaining issues to review", "Heading1")
    remaining = [(column, issue) for column in after.get("columns", []) for issue in column.get("issues", [])]
    if not remaining:
        add("No column issues detected by the current checks. This does not guarantee that every value is correct.")
    for column, issue in remaining:
        add(f"{column['column_name']}: {name(issue['issue'])} — {issue['count']} flagged values")
        if issue.get("examples"):
            add("Examples: " + "; ".join(str(value) for value in issue["examples"]))
    add("How to read this report", "Heading1")
    add("Affected counts are per step; a cell may be counted in multiple steps. Missing-value counts include recognized missing markers. Imputed values are estimates, not verified observations. Examples are samples, not an exhaustive list of changed cells. No exchange-rate conversion is performed.")

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#657382"))
        canvas.drawString(42, 25, "DataNeat | Your original file is preserved")
        canvas.drawRightString(A4[0] - 42, 25, f"Page {doc.page}")

    SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=44, title="DataNeat cleaning report").build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer

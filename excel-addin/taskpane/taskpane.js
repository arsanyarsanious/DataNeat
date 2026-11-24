/* DataNeat Excel add-in — Tier L read-only analyzer preview. */
(() => {
  "use strict";

  const isMock = new URLSearchParams(location.search).has("mock");
  const HIGHLIGHT_CELL_LIMIT = 10000;
  const READ_CHUNK_ROWS = 15000;
  const TIER_L_CELLS = 3000000;
  const BACKUP_KEY = "dataneat.excel.highlightBackup";

  const ISSUE_LABELS = {
    missing: "Missing", missing_marker: "Missing labels", whitespace: "Whitespace",
    capitalization: "Capitalization", boolean: "Boolean labels", invalid_date: "Invalid date",
    ambiguous_date: "Ambiguous date", date_format: "Mixed dates", time: "Clock time",
    invalid_time: "Invalid time", duration: "Duration", invalid_duration: "Invalid duration",
    currency: "Currency", percentage: "Percentage", percentage_scale: "Bare %",
    symbol: "Units", phone: "Phone", type: "Type", odd_value: "Unusual value",
    duplicate: "Duplicate row", email: "Email", data_format: "Data format",
    invalid_data_format: "Invalid format", rule_negative: "Negative value",
  };

  const ISSUE_ALIASES = {
    missing_values: "missing", extra_whitespace: "whitespace",
    case_inconsistency: "capitalization", boolean_inconsistency: "boolean",
    date_format_inconsistency: "date_format", ambiguous_dates: "ambiguous_date",
    invalid_dates: "invalid_date", time_format: "time", duration_format: "duration",
    currency_inconsistency: "currency", percentage_inconsistency: "percentage",
    symbol_inconsistency: "symbol", phone_inconsistency: "phone", invalid_phone: "phone",
    type_mismatch: "type",
  };

  function normalizeKind(kind) {
    return ISSUE_ALIASES[kind] || kind;
  }

  const FILL_COLORS = {
    missing: "#FDE68A", missing_marker: "#FDE68A",
    invalid_date: "#BFDBFE", ambiguous_date: "#BFDBFE", date_format: "#BFDBFE",
    time: "#BFDBFE", invalid_time: "#BFDBFE", duration: "#BFDBFE", invalid_duration: "#BFDBFE",
    currency: "#DDD6FE", percentage: "#DDD6FE", percentage_scale: "#DDD6FE", symbol: "#DDD6FE",
    phone: "#FBCFE8", email: "#FBCFE8",
    whitespace: "#BBF7D0", capitalization: "#BBF7D0", boolean: "#BBF7D0",
    type: "#FECACA", odd_value: "#FECACA", data_format: "#FECACA", invalid_data_format: "#FECACA",
    duplicate: "#FED7AA", rule_negative: "#FED7AA",
  };

  const $ = (id) => document.getElementById(id);
  const statusEl = $("status");
  const analyzeButton = $("analyze");
  const highlightButton = $("highlight");
  const clearButton = $("clear");
  const hasHeader = $("hasHeader");
  const summary = $("summary");
  const issues = $("issues");

  let state = null;
  let busy = false;

  function setStatus(text, kind = "") {
    statusEl.textContent = text;
    statusEl.className = `status${kind ? ` ${kind}` : ""}`;
  }

  function setBusy(next) {
    busy = next;
    analyzeButton.disabled = next;
    highlightButton.disabled = next || !state?.analysis;
    clearButton.disabled = next;
    analyzeButton.textContent = next ? "Analyzing…" : "Analyze active sheet";
  }

  function escapeCsv(value) {
    const text = value == null ? "" : String(value);
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }

  function makeCsv(headers, rows) {
    const lines = [headers.map(escapeCsv).join(",")];
    for (const row of rows) lines.push(row.map(escapeCsv).join(","));
    return lines.join("\n") + "\n";
  }

  function issueTotal(column) {
    return (column.issues || []).reduce((sum, item) => sum + (item.count || 0), 0);
  }

  function issueLabel(kind) {
    const canonical = normalizeKind(kind);
    return ISSUE_LABELS[canonical] || kind.replaceAll("_", " ");
  }

  function render(analysis) {
    state = { ...(state || {}), analysis, headerOffset: hasHeader.checked ? 1 : 0 };
    $("metricRows").textContent = analysis.rows.toLocaleString();
    $("metricCols").textContent = analysis.columns_count.toLocaleString();
    $("metricCells").textContent = analysis.cells_count.toLocaleString();
    $("metricIssues").textContent = analysis.total_issue_cells.toLocaleString();
    summary.hidden = false;
    issues.hidden = false;

    const truncated = $("truncated");
    const shown = Math.min(analysis.cells.length, HIGHLIGHT_CELL_LIMIT);
    if (analysis.truncated || analysis.cells.length > HIGHLIGHT_CELL_LIMIT) {
      truncated.hidden = false;
      truncated.textContent = `Showing the first ${shown.toLocaleString()} flagged cells of ${analysis.total_issue_cells.toLocaleString()}. Column totals are complete.`;
    } else {
      truncated.hidden = true;
    }
    $("capNote").textContent = `This preview highlights up to ${HIGHLIGHT_CELL_LIMIT.toLocaleString()} cells per run. Tier L supports up to ${TIER_L_CELLS.toLocaleString()} cells.`;

    const sorted = [...analysis.columns].sort((a, b) => issueTotal(b) - issueTotal(a));
    const withIssues = sorted.filter((column) => issueTotal(column) > 0);
    $("issueCount").textContent = `${withIssues.length} of ${analysis.columns_count} columns`;
    $("issueRows").innerHTML = withIssues.map((column) => {
      const chips = (column.issues || []).filter((item) => item.count > 0).map((item) =>
        `<span class="chip">${escapeHtml(issueLabel(item.kind))} <b>${item.count.toLocaleString()}</b></span>`
      ).join("");
      return `<tr><td title="${escapeHtml(column.name)}">${escapeHtml(column.name)}</td><td>${escapeHtml(column.detected_type)}</td><td><div class="chips">${chips}</div></td></tr>`;
    }).join("") || `<tr><td colspan="3">No issues found in this sheet.</td></tr>`;

    highlightButton.disabled = analysis.cells.length === 0;
    setBusy(false);
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  }

  async function postAnalysis(csv, filename = "excel-sheet.csv") {
    const form = new FormData();
    form.append("file", new Blob([csv], { type: "text/csv" }), filename);
    form.append("highlight_cap", String(HIGHLIGHT_CELL_LIMIT));
    const response = await fetch("/api/addin/analyze", { method: "POST", body: form });
    const text = await response.text();
    let body;
    try { body = JSON.parse(text); } catch { body = null; }
    if (!response.ok) {
      throw new Error(body?.detail || `Analysis failed (HTTP ${response.status}).`);
    }
    return body;
  }

  async function analyzeMock() {
    setStatus("Running the mock preview against the local engine…", "working");
    const headers = ["Customer_ID", "Name", "Phone", "Salary", "Active", "Birth_Date"];
    const rows = [
      ["1", " Cairo ", "+201001234567", "5000", "Yes", "15/05/1995"],
      ["2", "cairo", "01001234567", "6200", "TRUE", "03/07/2000"],
      ["3", "Kairo", "00201001234567", "N/A", "1", "N/A"],
      ["4", "Cairo", "+20 100 123 4567", "8200", "no", "05/10/1997"],
    ];
    const analysis = await postAnalysis(makeCsv(headers, rows));
    state = { analysis, headerOffset: 1, mock: true };
    render(analysis);
    highlightButton.disabled = true;
    setStatus("Mock preview ready. Highlighting is only available inside Excel.", "");
  }

  async function readSheet() {
    return Excel.run(async (context) => {
      const sheet = context.workbook.worksheets.getActiveWorksheet();
      const used = sheet.getUsedRange();
      context.workbook.load("name");
      used.load(["rowCount", "columnCount"]);
      await context.sync();

      const rows = used.rowCount;
      const columns = used.columnCount;
      if (!rows || !columns) throw new Error("The active sheet has no used range.");
      if (rows * columns > TIER_L_CELLS) {
        throw new Error(`This sheet has ${ (rows * columns).toLocaleString() } cells. Tier L supports up to ${TIER_L_CELLS.toLocaleString()}; select a smaller range or split the sheet.`);
      }

      const data = [];
      for (let start = 0; start < rows; start += READ_CHUNK_ROWS) {
        const count = Math.min(READ_CHUNK_ROWS, rows - start);
        setStatus(`Reading rows ${(start + 1).toLocaleString()}–${(start + count).toLocaleString()} of ${rows.toLocaleString()}…`, "working");
        const range = used.getCell(start, 0).getResizedRange(count - 1, columns - 1);
        range.load("text");
        await context.sync();
        for (const row of range.text) data.push(row);
      }

      return { rows, columns, data, workbookName: context.workbook.name || "" };
    });
  }

  async function analyzeExcel() {
    const hasHeaders = hasHeader.checked;
    const sheet = await readSheet();
    let headers;
    let dataRows;
    if (hasHeaders) {
      headers = sheet.data[0].map((value, index) => {
        const text = String(value ?? "").trim();
        return text || `Column ${index + 1}`;
      });
      dataRows = sheet.data.slice(1);
    } else {
      headers = Array.from({ length: sheet.columns }, (_, index) => `Column ${index + 1}`);
      dataRows = sheet.data;
    }
    if (!dataRows.length) throw new Error("This sheet has no data rows under the selected header setting.");

    setStatus("Sending the sheet to the local DataNeat engine…", "working");
    const csv = makeCsv(headers, dataRows);
    const analysis = await postAnalysis(csv);
    state = { analysis, headerOffset: hasHeaders ? 1 : 0, sheet };
    render(analysis);
    setStatus(`Analysis ready: ${analysis.total_issue_cells.toLocaleString()} flagged cells in ${analysis.columns_count} columns. Highlight them or review the table.`);
  }

  async function analyze() {
    if (busy) return;
    setBusy(true);
    setStatus(isMock ? "Preparing mock sheet…" : "Reading the active sheet…", "working");
    try {
      if (isMock) await analyzeMock();
      else await analyzeExcel();
    } catch (error) {
      setBusy(false);
      setStatus(error.message || String(error), "error");
    }
  }

  function chooseColor(kinds) {
    for (const kind of kinds || []) {
      const canonical = normalizeKind(kind);
      if (FILL_COLORS[canonical]) return FILL_COLORS[canonical];
    }
    return "#FED7AA";
  }

  function buildRuns(cells, headerOffset) {
    const sorted = [...cells].sort((a, b) => a.row - b.row || a.column - b.column);
    const runs = [];
    for (const cell of sorted) {
      const color = chooseColor(cell.kinds);
      const row = cell.row + headerOffset;
      const last = runs[runs.length - 1];
      if (last && last.row === row && last.end + 1 === cell.column && last.color === color) {
        last.end = cell.column;
        last.length += 1;
      } else {
        runs.push({ row, start: cell.column, end: cell.column, length: 1, color });
      }
    }
    return runs;
  }

  function saveBackup(backup) {
    const json = JSON.stringify(backup);
    try {
      Office.context.document.settings.set(BACKUP_KEY, json);
      Office.context.document.settings.saveAsync(() => {});
      return true;
    } catch {
      try { localStorage.setItem(BACKUP_KEY, json); return true; } catch { return false; }
    }
  }

  function loadBackup() {
    try {
      const fromSettings = Office.context.document.settings.get(BACKUP_KEY);
      if (fromSettings) return JSON.parse(fromSettings);
    } catch { /* Settings may be unavailable in mock/browser mode. */ }
    try {
      const raw = localStorage.getItem(BACKUP_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }

  function clearBackup() {
    try { Office.context.document.settings.remove(BACKUP_KEY); Office.context.document.settings.saveAsync(() => {}); } catch { /* ignore */ }
    try { localStorage.removeItem(BACKUP_KEY); } catch { /* ignore */ }
  }

  async function highlightIssues() {
    if (!state?.analysis || state.mock) return;
    const cells = state.analysis.cells.slice(0, HIGHLIGHT_CELL_LIMIT);
    if (!cells.length) { setStatus("No flagged cells to highlight.", ""); return; }
    setBusy(true);
    setStatus(`Painting ${cells.length.toLocaleString()} highlighted cells…`, "working");
    const runs = buildRuns(cells, state.headerOffset);
    const workbook = state.sheet?.workbookName || "";
    let backup = [];
    let canRestore = true;
    let stage = "read original fills";
    try {
      try {
        await Excel.run(async (context) => {
          const sheet = context.workbook.worksheets.getActiveWorksheet();
          sheet.load("name");
          const used = sheet.getUsedRange();
          const proxies = runs.map((run) => {
            const range = used.getCell(run.row, run.start).getResizedRange(0, run.length - 1);
            range.load("address");
            range.format.fill.load("color");
            return range;
          });
          await context.sync();
          backup = proxies.map((range) => ({
            address: range.address.split("!").pop(),
            color: range.format.fill.color || null,
          }));
          canRestore = saveBackup({ workbook, worksheet: sheet.name, created: new Date().toISOString(), items: backup });
        });
      } catch {
        canRestore = false;
        backup = [];
      }

      stage = "apply fills";
      await Excel.run(async (context) => {
        const sheet = context.workbook.worksheets.getActiveWorksheet();
        const used = sheet.getUsedRange();
        for (const run of runs) {
          const range = used.getCell(run.row, run.start).getResizedRange(0, run.length - 1);
          range.format.fill.color = run.color;
        }
        await context.sync();
      });
      setBusy(false);
      setStatus(
        canRestore
          ? `Highlighted ${cells.length.toLocaleString()} cells. Use “Clear highlights” to restore the previous fills.`
          : `Highlighted ${cells.length.toLocaleString()} cells, but Excel settings could not store the original fills. Clearing will remove the fills rather than restore them.`,
        canRestore ? "" : "error",
      );
    } catch (error) {
      setBusy(false);
      const message = error.message || String(error);
      if (/cannot perform the requested operation|AccessDenied/i.test(message)) {
        setStatus(
          "Excel blocked the highlight write. Make sure the workbook is editable (not Protected View or read-only) and Excel is signed in and licensed, then retry.",
          "error",
        );
      } else {
        setStatus(`Highlight failed while ${stage}: ${message}`, "error");
      }
    }
  }

  async function clearHighlights() {
    if (busy) return;
    const backup = loadBackup();
    if (!backup?.items?.length) {
      setStatus("No DataNeat highlights were found in this workbook.", "");
      return;
    }
    setBusy(true);
    setStatus(`Restoring ${backup.items.length.toLocaleString()} cells…`, "working");
    try {
      await Excel.run(async (context) => {
        const sheet = context.workbook.worksheets.getActiveWorksheet();
        for (const item of backup.items) {
          const range = sheet.getRange(item.address);
          if (item.color) range.format.fill.color = item.color;
          else range.format.fill.clear();
        }
        await context.sync();
      });
      clearBackup();
      setBusy(false);
      setStatus("Highlights cleared and previous fills restored.", "");
    } catch (error) {
      setBusy(false);
      setStatus(error.message || String(error), "error");
    }
  }

  function bind() {
    analyzeButton.addEventListener("click", analyze);
    highlightButton.addEventListener("click", highlightIssues);
    clearButton.addEventListener("click", clearHighlights);
  }

  if (isMock) {
    bind();
    setStatus("Mock preview. Analyze the sample sheet to check the interface; highlighting requires Excel.", "");
    $("capNote").textContent = `Mock mode uses a small sample. In Excel, Tier L supports up to ${TIER_L_CELLS.toLocaleString()} cells and highlights up to ${HIGHLIGHT_CELL_LIMIT.toLocaleString()} cells.`;
  } else if (typeof Office !== "undefined") {
    Office.onReady((info) => {
      if (info.host === Office.HostType.Excel) {
        bind();
        setStatus("Ready. Make sure the sheet has headers, then analyze.");
      } else {
        setStatus("Open this add-in inside Excel to analyze a worksheet.", "error");
      }
    });
  } else {
    setStatus("Office.js did not load. Open this task pane inside Excel.", "error");
  }
})();

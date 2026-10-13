"use client";
import { useEffect, useRef, useState } from "react";
import { api, type Preview, type Profile } from "@/lib/types";
import { Button } from "./ui/button";
type CellIssue = { kind: string; message: string };
type Sheet = {
  preview: Preview & { row_indices: number[]; cell_issues: CellIssue[][][] };
  profile: Profile;
  revision: number;
  basic_log: { operation: string; column: string; modified_values: number }[];
  changes: unknown[];
};
type Selection = {
  row: number;
  column: string;
  value: unknown;
  issues: CellIssue[];
  left: number;
  top: number;
};
type Proposal = {
  changed_cells: number;
  examples: { row_index: number; before: unknown; after: unknown }[];
  warnings: string[];
};
const issueNames: Record<string, string> = {
  whitespace: "Extra whitespace",
  missing: "Missing value",
  invalid_date: "Invalid date",
  ambiguous_date: "Ambiguous date",
  capitalization: "Capitalization",
  currency: "Currency notation",
  percentage: "Percentage notation",
  symbol: "Unit notation",
  phone: "Phone format",
  type: "Type mismatch",
  email: "Invalid email",
  duplicate: "Duplicate row",
};
const colors: Record<string, string> = {
  whitespace: "#6bc5db",
  missing: "#e4ad35",
  invalid_date: "#ed6b78",
  ambiguous_date: "#ab82ef",
  capitalization: "#53a4dd",
  currency: "#4abea7",
  percentage: "#d986cc",
  symbol: "#88b964",
  phone: "#eb9b58",
  type: "#9ba1ed",
  email: "#e777a3",
  duplicate: "#879bae",
};
export function InteractiveSheet({ fileId }: { fileId: string }) {
  const [sheet, setSheet] = useState<Sheet | null>(null),
    [selection, setSelection] = useState<Selection | null>(null);
  const [action, setAction] = useState("replace"),
    [scope, setScope] = useState("cell"),
    [value, setValue] = useState("");
  const [symbol, setSymbol] = useState("$"),
    [region, setRegion] = useState(""),
    [format, setFormat] = useState("add"),
    [group, setGroup] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const pinned = useRef(false),
    hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    let active = true;
    api<Sheet>(`/files/${fileId}/editor/start`, { method: "POST" })
      .then((s) => {
        if (active) setSheet(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
    };
  }, [fileId]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelection(null);
        pinned.current = false;
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  async function load(page: number) {
    setBusy(true);
    setError("");
    try {
      setSheet(await api<Sheet>(`/files/${fileId}/editor?page=${page}`));
      setSelection(null);
      pinned.current = false;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function open(cell: Selection, click = false) {
    if (busy || (!click && pinned.current)) return;
    if (click) pinned.current = true;
    setSelection(cell);
    setAction("replace");
    setScope("cell");
    setValue(cell.value == null ? "" : String(cell.value));
    setProposal(null);
    setError("");
  }
  function invalidate() {
    setProposal(null);
  }
  function parameters() {
    if (action === "normalize_dates")
      return { interpretation: format, include_time: false };
    if (action === "normalize_capitalization") return { strategy: format };
    if (action === "normalize_currency" || action === "normalize_symbols")
      return { action: format, symbol, position: "prefix", grouping: "remove" };
    if (action === "normalize_percentage") return { action: format };
    if (action === "normalize_phone")
      return { action: format, region: region.toUpperCase() };
    if (action === "impute_missing_values")
      return {
        method: format,
        group_by: group ? [group] : [],
        confirmed: true,
      };
    return {};
  }
  async function fix(confirmed: boolean) {
    if (!sheet || !selection) return;
    setBusy(true);
    setError("");
    try {
      const response = await api<{ proposal: Proposal }>(
        `/files/${fileId}/editor/fix`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            revision: sheet.revision,
            column: selection.column,
            row_index: selection.row,
            scope,
            action,
            value: value === "" ? null : value,
            parameters: parameters(),
            confirmed,
          }),
        },
      );
      if (confirmed) {
        setSheet(
          await api<Sheet>(
            `/files/${fileId}/editor?page=${sheet.preview.page}`,
          ),
        );
        setSelection(null);
        setProposal(null);
        pinned.current = false;
      } else {
        setProposal(response.proposal);
        pinned.current = true;
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!sheet)
    return (
      <section className="panel">
        <div className="panel-body">
          {error ? (
            <p role="alert">{error}</p>
          ) : (
            <p>Applying basic cleanup and preparing your spreadsheet…</p>
          )}
        </div>
      </section>
    );
  const available = selection
    ? Array.from(new Set(selection.issues.map((i) => i.kind)))
    : [];
  return (
    <section
      className="interactive-editor"
      aria-label="Interactive spreadsheet editor"
    >
      <div className="notice">
        Basic cleanup has been applied to a copy. Ambiguous dates, currency
        units, identifiers, and phone codes are preserved until you choose a
        fix.
      </div>
      <details className="panel editor-basic-log">
        <summary>
          Basic cleanup report (
          {sheet.basic_log.reduce((sum, l) => sum + l.modified_values, 0)}{" "}
          changes)
        </summary>
        {sheet.basic_log
          .filter((l) => l.modified_values)
          .map((l, i) => (
            <p key={i}>
              {l.column}: {l.operation.replaceAll("_", " ")} ·{" "}
              {l.modified_values} values
            </p>
          ))}
      </details>
      <div className="issue-legend" aria-label="Issue color legend">
        {Object.entries(issueNames).map(([kind, name]) => (
          <span key={kind}>
            <i style={{ background: colors[kind] }} />
            {name}
          </span>
        ))}
      </div>
      <p>
        Hover, click, or focus a highlighted cell to see its issues and fix
        choices. Multiple issues have multiple color markers. Changes require a
        preview and confirmation.
      </p>
      {!selection && error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="editor-downloads">
        <strong>
          {sheet.changes.length} confirmed actions · Revision {sheet.revision}
        </strong>
        {["xlsx", "csv", "report"].map((f) => (
          <a
            className="button outline"
            key={f}
            href={`/api/files/${fileId}/editor/download?format=${f}`}
            download
          >
            Download {f.toUpperCase()}
          </a>
        ))}
      </div>
      <div className="panel">
        <div className="table-scroll editor-table-scroll">
          <table className="editor-table">
            <thead>
              <tr>
                <th>#</th>
                {sheet.preview.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sheet.preview.rows.map((row, r) => (
                <tr key={sheet.preview.row_indices[r]}>
                  <td>{sheet.preview.row_indices[r] + 2}</td>
                  {row.map((v, c) => {
                    const issues = sheet.preview.cell_issues[r][c];
                    function cell(element: HTMLElement): Selection {
                      const rect = element.getBoundingClientRect();
                      const width = Math.min(380, window.innerWidth - 24);
                      return {
                        row: sheet!.preview.row_indices[r],
                        column: sheet!.preview.columns[c],
                        value: v,
                        issues,
                        left:
                          rect.right + width + 12 < window.innerWidth
                            ? rect.right + 8
                            : Math.max(12, rect.left - width - 8),
                        top: Math.max(
                          12,
                          Math.min(rect.top, window.innerHeight - 580),
                        ),
                      };
                    }
                    return (
                      <td
                        key={c}
                        style={
                          issues.length
                            ? { background: `${colors[issues[0].kind]}24` }
                            : undefined
                        }
                      >
                        {issues.length ? (
                          <button
                            className="issue-cell"
                            aria-label={`Issues in ${sheet.preview.columns[c]} row ${sheet.preview.row_indices[r] + 2}: ${issues.map((i) => issueNames[i.kind]).join(", ")}`}
                            onMouseEnter={(e) => {
                              if (hoverTimer.current)
                                clearTimeout(hoverTimer.current);
                              const selected = cell(e.currentTarget);
                              hoverTimer.current = setTimeout(
                                () => open(selected),
                                180,
                              );
                            }}
                            onMouseLeave={() => {
                              if (hoverTimer.current)
                                clearTimeout(hoverTimer.current);
                            }}
                            onClick={(e) => open(cell(e.currentTarget), true)}
                            onFocus={(e) => open(cell(e.currentTarget))}
                          >
                            <span className="cell-color-markers">
                              {issues.map((i, n) => (
                                <i
                                  key={n}
                                  style={{ background: colors[i.kind] }}
                                  title={issueNames[i.kind]}
                                />
                              ))}
                            </span>
                            {v == null || v === "" ? <em>empty</em> : String(v)}
                          </button>
                        ) : v == null || v === "" ? (
                          <em>empty</em>
                        ) : (
                          String(v)
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>
            {sheet.preview.total_rows} rows · Page {sheet.preview.page}
          </span>
          <div>
            <Button
              variant="outline"
              disabled={busy || sheet.preview.page === 1}
              onClick={() => load(sheet.preview.page - 1)}
            >
              Previous
            </Button>{" "}
            <Button
              variant="outline"
              disabled={
                busy ||
                sheet.preview.page * sheet.preview.page_size >=
                  sheet.preview.total_rows
              }
              onClick={() => load(sheet.preview.page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </div>
      {selection && (
        <div
          role="dialog"
          aria-label={`Fix ${selection.column} row ${selection.row + 2}`}
          className="cell-fix-panel"
          style={{ left: selection.left, top: selection.top }}
          onMouseEnter={() => {
            pinned.current = true;
          }}
        >
          <div className="panel-heading">
            <h3>
              {selection.column} · Row {selection.row + 2}
            </h3>
            <Button
              variant="ghost"
              onClick={() => {
                setSelection(null);
                pinned.current = false;
              }}
            >
              Close
            </Button>
          </div>
          <div className="panel-body">
            <ul>
              {selection.issues.map((i, n) => (
                <li key={n}>
                  <strong>{issueNames[i.kind]}:</strong> {i.message}
                </li>
              ))}
            </ul>
            <label className="setting">
              Fix option
              <select
                aria-label="Cell fix option"
                disabled={busy}
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  if (e.target.value === "replace") setScope("cell");
                  if (e.target.value === "remove_duplicates")
                    setScope("column");
                  setFormat(
                    e.target.value === "normalize_dates"
                      ? "day_first"
                      : e.target.value === "normalize_capitalization"
                        ? "title"
                        : e.target.value === "impute_missing_values"
                          ? "mode"
                          : e.target.value === "normalize_phone"
                            ? "international"
                            : "add",
                  );
                  invalidate();
                }}
              >
                <option value="replace">
                  Enter a corrected value / clear cell
                </option>
                {available.includes("whitespace") && (
                  <option value="trim_whitespace">Trim extra whitespace</option>
                )}
                {available.includes("ambiguous_date") && (
                  <option value="normalize_dates">
                    Confirm date interpretation
                  </option>
                )}
                {available.includes("capitalization") && (
                  <option value="normalize_capitalization">
                    Standardize capitalization
                  </option>
                )}
                {available.includes("currency") && (
                  <option value="normalize_currency">
                    Standardize currency notation
                  </option>
                )}
                {available.includes("percentage") && (
                  <option value="normalize_percentage">
                    Include or remove %
                  </option>
                )}
                {available.includes("symbol") && (
                  <option value="normalize_symbols">
                    Standardize unit notation
                  </option>
                )}
                {available.includes("phone") && (
                  <option value="normalize_phone">
                    Standardize phone format
                  </option>
                )}
                {available.includes("type") && (
                  <option value="normalize_boolean">
                    Recognized boolean labels
                  </option>
                )}
                {available.includes("missing") && (
                  <option value="impute_missing_values">
                    Fill missing cells with an estimate
                  </option>
                )}
                {available.includes("duplicate") && (
                  <option value="remove_duplicates">
                    Remove full duplicate rows (dataset)
                  </option>
                )}
              </select>
            </label>
            <label className="setting">
              Apply to
              <select
                aria-label="Fix scope"
                value={scope}
                disabled={busy || action === "replace"}
                onChange={(e) => {
                  setScope(e.target.value);
                  invalidate();
                }}
              >
                <option value="cell">This cell</option>
                <option value="column">
                  This column (dataset for duplicate removal)
                </option>
              </select>
            </label>
            {action === "replace" && (
              <label className="setting">
                Corrected value
                <input
                  aria-label="Corrected cell value"
                  value={value}
                  disabled={busy}
                  onChange={(e) => {
                    setValue(e.target.value);
                    invalidate();
                  }}
                />
                <small>
                  Leave blank to clear the cell. Other existing values are
                  preserved.
                </small>
              </label>
            )}
            {action !== "replace" &&
              action !== "remove_duplicates" &&
              action !== "normalize_boolean" &&
              action !== "trim_whitespace" && (
                <label className="setting">
                  Desired format
                  <select
                    aria-label="Cell fix format"
                    value={format}
                    disabled={busy}
                    onChange={(e) => {
                      setFormat(e.target.value);
                      invalidate();
                    }}
                  >
                    {(action === "normalize_dates"
                      ? ["day_first", "month_first"]
                      : action === "normalize_capitalization"
                        ? ["title", "upper", "lower"]
                        : action === "impute_missing_values"
                          ? [
                              "mode",
                              ...(sheet.profile.columns
                                .find((c) => c.column_name === selection.column)
                                ?.imputation?.available_methods.includes("mean")
                                ? ["mean", "median"]
                                : []),
                            ]
                          : action === "normalize_phone"
                            ? [
                                "international",
                                "international_digits",
                                "national",
                                "remove_plus",
                                "add_plus",
                              ]
                            : ["add", "remove"]
                    ).map((f) => (
                      <option key={f} value={f}>
                        {f.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            {(action === "normalize_currency" ||
              action === "normalize_symbols") &&
              format === "add" && (
                <label className="setting">
                  Symbol
                  <input
                    aria-label="Cell currency symbol"
                    disabled={busy}
                    value={symbol}
                    onChange={(e) => {
                      setSymbol(e.target.value);
                      invalidate();
                    }}
                  />
                </label>
              )}
            {action === "normalize_phone" && (
              <label className="setting">
                Country (ISO code)
                <input
                  aria-label="Cell phone country"
                  disabled={busy}
                  maxLength={2}
                  placeholder="EG, US, GB…"
                  value={region}
                  onChange={(e) => {
                    setRegion(e.target.value);
                    invalidate();
                  }}
                />
              </label>
            )}
            {action === "impute_missing_values" && (
              <label className="setting">
                Group by (optional)
                <select
                  aria-label="Cell imputation group"
                  disabled={busy}
                  value={group}
                  onChange={(e) => {
                    setGroup(e.target.value);
                    invalidate();
                  }}
                >
                  <option value="">Whole column</option>
                  {sheet.preview.columns
                    .filter((c) => c !== selection.column)
                    .map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                </select>
              </label>
            )}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            {!proposal ? (
              <Button disabled={busy} onClick={() => fix(false)}>
                Preview fix
              </Button>
            ) : (
              <div className="cell-confirmation">
                <h4>Confirm this change</h4>
                <p>{proposal.changed_cells} cells / rows would change.</p>
                {proposal.examples.map((e, i) => (
                  <p key={i}>
                    Row {e.row_index + 2}:{" "}
                    <code>{String(e.before ?? "empty")}</code> →{" "}
                    <code>{String(e.after ?? "empty")}</code>
                  </p>
                ))}
                {proposal.warnings.map((w) => (
                  <p key={w}>{w}</p>
                ))}
                <Button
                  disabled={busy || !proposal.changed_cells}
                  onClick={() => fix(true)}
                >
                  Confirm and apply
                </Button>{" "}
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => setProposal(null)}
                >
                  Cancel
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

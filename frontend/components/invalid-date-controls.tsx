"use client";
import { useEffect, useState } from "react";
import { api, type Operation, type InvalidDateRows } from "@/lib/types";
import { Button } from "./ui/button";
export function InvalidDateControls({
  fileId,
  operation,
  onChange,
  disabled,
}: {
  fileId: string;
  operation: Operation;
  onChange: (parameters: Record<string, unknown>) => void;
  disabled: boolean;
}) {
  const [page, setPage] = useState(1),
    [data, setData] = useState<InvalidDateRows | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const action = String(operation.parameters.action || "manual");
  const replacements = (operation.parameters.replacements || {}) as Record<
    string,
    string | null
  >;
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void api<InvalidDateRows>(
      `/files/${fileId}/invalid-dates?column=${encodeURIComponent(operation.column!)}&page=${page}`,
    )
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [fileId, operation.column, page]);
  function change(row: number, value: string | null | undefined) {
    const next = { ...replacements };
    if (value === undefined) delete next[String(row)];
    else next[String(row)] = value;
    onChange({ ...operation.parameters, replacements: next });
  }
  return (
    <div className="invalid-date-controls">
      <label className="setting">
        How to resolve invalid dates
        <select
          aria-label={`Invalid date action for ${operation.column}`}
          disabled={disabled}
          value={action}
          onChange={(e) =>
            onChange({ ...operation.parameters, action: e.target.value })
          }
        >
          <option value="manual">Correct individual rows manually</option>
          <option value="empty">
            Replace all invalid dates with empty cells
          </option>
        </select>
      </label>
      {action === "empty" ? (
        <div className="date-clear-warning">
          Only invalid, nonempty cells in this column will be cleared. Valid and
          ambiguous dates are preserved. Enable this operation to approve the
          change.
        </div>
      ) : (
        <>
          <p className="manual-date-note">
            Enter a real date in YYYY-MM-DD format, or explicitly choose an
            empty cell. Rows you leave unedited keep their original values. Row
            numbers include the header row.
          </p>
          {error && (
            <p role="alert" className="warning-text">
              {error}
            </p>
          )}
          {loading ? (
            <p>Loading invalid dates…</p>
          ) : (
            data && (
              <>
                <div className="table-scroll">
                  <table className="date-edit-table">
                    <thead>
                      <tr>
                        <th>Spreadsheet row</th>
                        <th>Invalid value</th>
                        <th>Corrected date</th>
                        <th>Replace with empty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.rows.map((row) => (
                        <tr key={row.row_index}>
                          <td>{row.spreadsheet_row}</td>
                          <td>
                            <code>{String(row.value)}</code>
                          </td>
                          <td>
                            <input
                              type="date"
                              aria-label={`Corrected date for ${operation.column} row ${row.spreadsheet_row}`}
                              disabled={
                                disabled ||
                                replacements[String(row.row_index)] === null
                              }
                              value={replacements[String(row.row_index)] || ""}
                              onChange={(e) =>
                                change(
                                  row.row_index,
                                  e.target.value || undefined,
                                )
                              }
                            />
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Empty ${operation.column} row ${row.spreadsheet_row}`}
                              disabled={disabled}
                              checked={
                                replacements[String(row.row_index)] === null
                              }
                              onChange={(e) =>
                                change(
                                  row.row_index,
                                  e.target.checked ? null : undefined,
                                )
                              }
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="table-footer">
                  <span>
                    {data.total} invalid dates ·{" "}
                    {Object.keys(replacements).length} corrections selected
                  </span>
                  <div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={disabled || loading || page === 1}
                      onClick={() => setPage(page - 1)}
                    >
                      Previous invalid dates
                    </Button>{" "}
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={
                        disabled ||
                        loading ||
                        page * data.page_size >= data.total
                      }
                      onClick={() => setPage(page + 1)}
                    >
                      Next invalid dates
                    </Button>
                  </div>
                </div>
              </>
            )
          )}
        </>
      )}
    </div>
  );
}

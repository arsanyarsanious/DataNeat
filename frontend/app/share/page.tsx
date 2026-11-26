"use client";
import { useEffect, useState } from "react";
import { FileDown, Moon, ShieldCheck, Sun } from "lucide-react";
import { DataNeatMark } from "@/components/dataneat-mark";
import { LoadingOverlay } from "@/components/loading-skeleton";
import { api } from "@/lib/types";
import "./share.css";

type Change = { action: string; column: string; changed_cells: number };
type ShareView = {
  filename: string;
  revision: number;
  rows: number;
  columns: number;
  changes: Change[];
  issues?: { cells?: number; columns?: number; types?: number };
  preview: {
    columns: string[];
    rows: (string | number | null)[][];
    total_rows: number;
  };
  expires_at: number;
  read_only: boolean;
};

export default function SharePage() {
  const [token, setToken] = useState("");
  const [view, setView] = useState<ShareView | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const theme = localStorage.getItem("dataneat-theme") !== "light";
    setDark(theme);
    document.documentElement.classList.toggle("dark", theme);
    const value = new URLSearchParams(window.location.search).get("t") || "";
    setToken(value);
    if (!value) {
      setError("This review link is missing its token.");
      setLoading(false);
      return;
    }
    api<ShareView>(`/share/${encodeURIComponent(value)}`)
      .then(setView)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("dataneat-theme", next ? "dark" : "light");
  }

  const expires = view ? new Date(view.expires_at * 1000).toLocaleString() : "";

  return (
    <LoadingOverlay loading={loading} variant="share" label="Opening the shared review...">
    <main className="share-page">
      <header className="share-topbar">
        <div className="share-brand">
          <DataNeatMark size={30} />
          <span>DataNeat</span>
          <span className="share-tag">Read-only review</span>
        </div>
        <button
          className="share-icon-button"
          type="button"
          onClick={toggleTheme}
          aria-label={dark ? "Use light theme" : "Use dark theme"}
        >
          {dark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
        </button>
      </header>
      <section className="share-card">
        {loading && <p role="status">Opening the shared review…</p>}
        {!loading && error && (
          <div className="share-error" role="alert">
            <h1>This review link is not available</h1>
            <p>{error}</p>
            <p>
              Ask the person who shared it for a new link. The link may have
              expired, been revoked, or the file may have been deleted.
            </p>
            <a className="share-text-link" href="/">
              Go to DataNeat
            </a>
          </div>
        )}
        {!loading && view && (
          <>
            <div className="share-heading">
              <div>
                <p className="share-eyebrow">
                  Shared review · Revision {view.revision}
                </p>
                <h1>{view.filename}</h1>
                <p className="share-subtitle">
                  Opened from a read-only link. The owner&apos;s original upload is
                  preserved separately.
                </p>
              </div>
              <a
                className="share-button primary"
                href={`/api/share/${encodeURIComponent(token)}/report`}
                download
              >
                <FileDown size={16} aria-hidden="true" /> Download PDF report
              </a>
            </div>
            <dl className="share-metrics">
              <div>
                <dt>Rows</dt>
                <dd>{view.rows.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Columns</dt>
                <dd>{view.columns.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Recorded steps</dt>
                <dd>{view.changes.length.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Cells still flagged</dt>
                <dd>{(view.issues?.cells ?? 0).toLocaleString()}</dd>
              </div>
            </dl>
            {view.changes.length > 0 && (
              <section className="share-section">
                <h2>Recorded cleaning steps</h2>
                <ol>
                  {view.changes.map((change, index) => (
                    <li key={index}>
                      {change.action.replaceAll("_", " ")} · {change.column} ·{" "}
                      {change.changed_cells} cells / rows
                    </li>
                  ))}
                </ol>
              </section>
            )}
            {(view.issues?.cells ?? 0) > 0 && (
              <section className="share-section">
                <h2>Still flagged for review</h2>
                <p>
                  {(view.issues?.cells ?? 0).toLocaleString()} cells still have
                  review flags. A flag is a reason to review a value, not proof
                  that it is wrong.
                </p>
              </section>
            )}
            <section className="share-section">
              <h2>
                Preview · first {view.preview.rows.length} of{" "}
                {view.preview.total_rows.toLocaleString()} rows
              </h2>
              <div className="share-table-wrap" role="region" aria-label="Shared spreadsheet preview" tabIndex={0}>
                <table className="share-table">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      {view.preview.columns.map((column) => (
                        <th key={column} scope="col" title={column}>
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {view.preview.rows.map((row, index) => (
                      <tr key={index}>
                        <th scope="row">{index + 2}</th>
                        {row.map((value, column) => (
                          <td key={column}>
                            {value === null || value === "" ? (
                              <em>empty</em>
                            ) : (
                              String(value)
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <p className="share-footnote">
              <ShieldCheck size={15} aria-hidden="true" />
              <span>
                Read-only view. Anyone with this link can see these values until{" "}
                {expires} or until the owner revokes it. Editing, the original
                workbook and the owner&apos;s workspace are not available.
              </span>
            </p>
          </>
        )}
      </section>
    </main>
    </LoadingOverlay>
  );
}

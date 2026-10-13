"use client";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Database,
  Download,
  FileSpreadsheet,
  Layers3,
  Loader2,
  Moon,
  Plus,
  ShieldCheck,
  Sparkles,
  Sun,
  Trash2,
  UploadCloud,
  WandSparkles,
  X,
  AlertTriangle,
  SearchCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { InteractiveSheet } from "@/components/interactive-sheet";
import { DataTable } from "@/components/data-table";
import { ColumnAnalysis } from "@/components/column-analysis";
import { InvalidDateControls } from "@/components/invalid-date-controls";
import { CurrencyControls } from "@/components/currency-controls";
import { PercentageControls } from "@/components/percentage-controls";
import { PlanSelection } from "@/components/plan-selection";
import { PhoneControls } from "@/components/phone-controls";
import { ImputationControls } from "@/components/imputation-controls";
import { ImputationAudit } from "@/components/imputation-audit";
import { SymbolControls } from "@/components/symbol-controls";
import {
  api,
  initializeSession,
  type Upload,
  type Operation,
  type Results,
  type Preview,
  type Log,
  type Validation,
} from "@/lib/types";
const label = (text: string) =>
  text.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
export default function Home() {
  const [stage, setStage] = useState<
    "upload" | "profile" | "configure" | "results" | "editor"
  >("upload");
  const [uploaded, setUploaded] = useState<Upload | null>(null),
    [file, setFile] = useState<File | null>(null),
    [operations, setOperations] = useState<Operation[]>([]),
    [results, setResults] = useState<Results | null>(null),
    [job, setJob] = useState("");
  const [busy, setBusy] = useState(false),
    [progress, setProgress] = useState(0),
    [error, setError] = useState(""),
    [drag, setDrag] = useState(false),
    [dark, setDark] = useState(false),
    [comparison, setComparison] = useState<{
      before: Preview;
      after: Preview;
      operations: Log[];
      validation: Validation;
    } | null>(null);
  const [uploadLimit, setUploadLimit] = useState(20);
  const [interactive, setInteractive] = useState(false);
  const input = useRef<HTMLInputElement>(null),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    void initializeSession()
      .then((data) => setUploadLimit(data.max_upload_mb))
      .catch(() => {});
    const value = localStorage.getItem("dataneat-theme") === "dark";
    setDark(value);
    document.documentElement.classList.toggle("dark", value);
    return () => {
      mounted.current = false;
    };
  }, []);
  function theme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("dataneat-theme", next ? "dark" : "light");
  }
  async function upload(selected: File, sheet?: string) {
    if (!/\.(csv|xlsx)$/i.test(selected.name)) {
      setError("Choose a CSV or XLSX spreadsheet.");
      return;
    }
    if (selected.size > uploadLimit * 1024 * 1024) {
      setError(`This file exceeds the ${uploadLimit} MB upload limit.`);
      return;
    }
    setBusy(true);
    setError("");
    setProgress(0);
    setComparison(null);
    setResults(null);
    const form = new FormData();
    form.append("file", selected);
    if (sheet) form.append("sheet", sheet);
    try {
      await initializeSession();
      const response = await new Promise<Upload>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/files/upload");
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable)
            setProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
          try {
            const data = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300) resolve(data);
            else
              reject(
                new Error(
                  typeof data.detail === "string"
                    ? data.detail
                    : "Could not read spreadsheet",
                ),
              );
          } catch {
            reject(new Error("Server returned an invalid response"));
          }
        };
        xhr.onerror = () =>
          reject(new Error("Unable to reach the server. Please retry."));
        xhr.send(form);
      });
      if (uploaded)
        await api(`/files/${uploaded.file_id}`, { method: "DELETE" });
      setUploaded(response);
      setOperations(response.plan);
      setFile(selected);
      setStage(interactive ? "editor" : "profile");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function update(id: string, patch: Partial<Operation>) {
    setOperations((items) =>
      items.map((o) => {
        const next = o.id === id ? { ...o, ...patch } : o;
        return next.operation === "impute_missing_values"
          ? { ...next, parameters: { ...next.parameters, confirmed: false } }
          : next;
      }),
    );
    setComparison(null);
  }
  async function preview() {
    if (!uploaded) return;
    setBusy(true);
    setError("");
    try {
      setComparison(
        await api(`/files/${uploaded.file_id}/preview-cleaning`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operations }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function clean() {
    if (!uploaded) return;
    if (
      operations.some(
        (o) =>
          o.enabled &&
          o.operation === "impute_missing_values" &&
          o.parameters.method !== "preserve" &&
          (!comparison || o.parameters.confirmed !== true),
      )
    ) {
      setError(
        "Preview the selected imputation methods and confirm each column before applying.",
      );
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await api<{ job_id: string }>(
        `/files/${uploaded.file_id}/clean`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operations }),
        },
      );
      setJob(response.job_id);
      let completed = false;
      for (let i = 0; i < 300 && mounted.current; i++) {
        const status = await api<{ status: string; error?: string }>(
          `/jobs/${response.job_id}`,
        );
        if (status.status === "failed") throw new Error(status.error);
        if (status.status === "completed") {
          setResults(await api<Results>(`/jobs/${response.job_id}/results`));
          setStage("results");
          completed = true;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      if (!completed && mounted.current)
        throw new Error("Cleaning is still running. Please retry later.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reset() {
    setError("");
    setBusy(true);
    try {
      if (uploaded)
        await api(`/files/${uploaded.file_id}`, { method: "DELETE" });
      setUploaded(null);
      setResults(null);
      setFile(null);
      setOperations([]);
      setComparison(null);
      setStage("upload");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function paginate(page: number) {
    if (!uploaded) return;
    setBusy(true);
    try {
      if (stage === "results")
        setResults(await api<Results>(`/jobs/${job}/results?page=${page}`));
      else {
        const data = await api<Preview>(
          `/files/${uploaded.file_id}/preview?page=${page}`,
        );
        setUploaded({ ...uploaded, preview: data });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const operationGroups = Array.from(new Set(operations.map((o) => o.column)))
    .sort((a, b) =>
      a === null
        ? 1
        : b === null
          ? -1
          : a.localeCompare(b, undefined, { numeric: true }),
    )
    .map((column) => ({
      column,
      operations: operations.filter((o) => o.column === column),
    }));
  const profile =
    stage === "results" ? results?.validation.after : uploaded?.profile;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand">
          <span className="brand-symbol">
            <Layers3 size={22} />
          </span>
          DataNeat<span className="beta">BETA</span>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <button
          className="nav-item active"
          onClick={() => (uploaded ? setStage("profile") : setStage("upload"))}
        >
          <WandSparkles size={18} />
          Data cleaner
          <span className="nav-dot" />
        </button>
        <div className="sidebar-card">
          <span className="mini-icon">
            <ShieldCheck size={20} />
          </span>
          <strong>Your data. Your control.</strong>
          <p>
            No external AI services. Your original file always stays intact.
          </p>
          <a href="#privacy">
            Our privacy approach <ArrowUpRight size={14} />
          </a>
        </div>
        <div className="sidebar-bottom">
          <span className="avatar">DN</span>
          <div>
            <strong>Personal workspace</strong>
            <small>No account needed</small>
          </div>
          <button
            className="icon-button"
            aria-label="Toggle dark mode"
            onClick={theme}
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <span>Data cleaner</span>
          </div>
          <div className="topbar-right">
            <span className="privacy-pill">
              <span />
              Private by design
            </span>
            <button
              className="icon-button"
              aria-label="Toggle theme"
              onClick={theme}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <a href="#help" className="help-link">
              <CircleHelp size={16} />
              Help
            </a>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span />
                LESS MESS. MORE POSSIBILITY.
              </div>
              <h1>
                {stage === "upload"
                  ? "Good data starts here."
                  : stage === "profile"
                    ? "Meet your data."
                    : stage === "configure"
                      ? "A little cleanup. A lot of clarity."
                      : stage === "editor"
                        ? "Your interactive spreadsheet."
                        : "Your data, looking better."}
              </h1>
              <p>
                {stage === "upload"
                  ? "Turn messy spreadsheets into clean, consistent data — without the busywork."
                  : stage === "profile"
                    ? "A clear picture of what’s in your spreadsheet, and what needs attention."
                    : stage === "configure"
                      ? "You’re in control. Review each suggestion before anything changes."
                      : stage === "editor"
                        ? "Review colored issues in your spreadsheet and confirm the fixes you choose."
                        : "Review what changed, see what remains, and take your spreadsheet with you."}
              </p>
            </div>
            {uploaded && (
              <Button variant="outline" onClick={reset} disabled={busy}>
                <Plus size={16} />
                New spreadsheet
              </Button>
            )}
          </div>
          <div className="stepper">
            {(["upload", "profile", "configure", "results"] as const).map(
              (item, i) => {
                const index = [
                  "upload",
                  "profile",
                  "configure",
                  "results",
                ].indexOf(stage === "editor" ? "configure" : stage);
                return (
                  <div
                    key={item}
                    className={`step ${i === index ? "current" : ""} ${i < index ? "complete" : ""}`}
                  >
                    <span className="step-number">
                      {i < index ? <Check size={14} /> : i + 1}
                    </span>
                    <span>
                      {
                        [
                          "Upload spreadsheet",
                          "Explore your data",
                          "Review & clean",
                          "Export results",
                        ][i]
                      }
                    </span>
                    {i < 3 && <div className="step-line" />}
                  </div>
                );
              },
            )}
          </div>
          {error && (
            <div className="error" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {stage === "upload" && (
            <label className="assumption-check interactive-mode-choice">
              <input
                type="checkbox"
                checked={interactive}
                onChange={(e) => setInteractive(e.target.checked)}
              />{" "}
              Interactive spreadsheet: basic cleanup first, then fix colored
              issues with confirmation.
            </label>
          )}
          {stage === "upload" ? (
            <>
              <section className="upload-card">
                <div className="section-heading">
                  <div className="heading-icon">
                    <UploadCloud size={20} />
                  </div>
                  <div>
                    <h2>Let’s clean your spreadsheet</h2>
                    <p>Bring your data. We’ll help you make sense of it.</p>
                  </div>
                  <span className="tag">CSV & EXCEL</span>
                </div>
                <div
                  className={`dropzone ${drag ? "dragging" : ""}`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDrag(true);
                  }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDrag(false);
                    if (!busy && e.dataTransfer.files[0])
                      void upload(e.dataTransfer.files[0]);
                  }}
                >
                  <div className="upload-art">
                    <div className="art-sheet left" />
                    <div className="art-sheet right" />
                    <div className="art-sheet center">
                      <FileSpreadsheet size={36} />
                      <span />
                      <span />
                      <span />
                    </div>
                    <span className="spark">
                      <Sparkles size={17} />
                    </span>
                  </div>
                  <h3>
                    {busy
                      ? "Analyzing your spreadsheet…"
                      : "Drop your spreadsheet here"}
                  </h3>
                  <p>or choose a file from your computer</p>
                  <Button
                    onClick={() => input.current?.click()}
                    disabled={busy}
                  >
                    {busy ? (
                      <Loader2 className="spin" size={17} />
                    ) : (
                      <Plus size={17} />
                    )}
                    Choose file
                  </Button>
                  <input
                    ref={input}
                    type="file"
                    accept=".csv,.xlsx"
                    aria-label="Choose spreadsheet"
                    hidden
                    onChange={(e) => {
                      const selected = e.target.files?.[0];
                      if (selected) void upload(selected);
                      e.target.value = "";
                    }}
                  />
                  <span className="file-hint">
                    CSV or XLSX <span>·</span> Up to {uploadLimit} MB
                  </span>
                  {busy && (
                    <div
                      className="upload-progress"
                      role="progressbar"
                      aria-valuenow={progress}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    >
                      <div style={{ width: `${progress}%` }} />
                      <span>
                        {progress === 100
                          ? "Upload complete · analyzing"
                          : `${progress}% uploaded`}
                      </span>
                    </div>
                  )}
                </div>
                <div className="upload-note">
                  <ShieldCheck size={16} />
                  <span>
                    Your files are private, never used for training, and
                    automatically deleted after 24 hours.
                  </span>
                </div>
              </section>
              <div className="feature-grid">
                <Feature
                  icon={<SearchCheck size={21} />}
                  title="Spot the hidden issues"
                  text="Find missing values, duplicates, mixed types, and inconsistent formats."
                />
                <Feature
                  icon={<WandSparkles size={21} />}
                  title="Clean with confidence"
                  text="Review smart suggestions. Decide what changes and what stays."
                />
                <Feature
                  icon={<Download size={21} />}
                  title="Ready for what’s next"
                  text="Export a standardized CSV or Excel file, with a clear cleaning report."
                />
              </div>
              <div className="bottom-note">
                <span className="tiny-spark">
                  <Sparkles size={15} />
                </span>
                <span>A cleaner spreadsheet. A clearer starting point.</span>
                <span className="line" />
              </div>
            </>
          ) : (
            <>
              {uploaded && (
                <div className="file-banner">
                  <span className="file-icon">
                    <FileSpreadsheet size={23} />
                  </span>
                  <div>
                    <strong>{uploaded.filename}</strong>
                    <small>
                      {file ? (file.size / 1024).toFixed(1) + " KB · " : ""}
                      {uploaded.profile.rows.toLocaleString()} rows · Original
                      preserved
                    </small>
                  </div>
                  {uploaded.metadata.sheets.length > 0 && (
                    <label className="sheet-select">
                      Worksheet
                      <select
                        aria-label="Worksheet"
                        disabled={busy}
                        value={uploaded.metadata.worksheet}
                        onChange={(e) =>
                          file && void upload(file, e.target.value)
                        }
                      >
                        {uploaded.metadata.sheets.map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </label>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={reset}
                    disabled={busy}
                  >
                    <Trash2 size={15} />
                    Delete file
                  </Button>
                </div>
              )}
              {stage === "editor" && uploaded && (
                <>
                  <div className="dashboard-actions">
                    <h2>Interactive spreadsheet</h2>
                    <Button
                      variant="outline"
                      onClick={() => setStage("profile")}
                    >
                      Back to analysis
                    </Button>
                  </div>
                  <InteractiveSheet fileId={uploaded.file_id} />
                </>
              )}
              {stage === "profile" && profile && uploaded && (
                <>
                  <Stats
                    values={[
                      ["Rows", profile.rows],
                      ["Columns", profile.columns_count],
                      ["Missing values", profile.missing_count],
                      ["Duplicate rows", profile.duplicate_rows],
                    ]}
                  />
                  <div className="dashboard-actions">
                    <div>
                      <h2>Data quality overview</h2>
                      <p>
                        {profile.issue_count} issue categories detected. Match
                        scores describe observed patterns, not probabilities.
                      </p>
                    </div>
                    <Button onClick={() => setStage("configure")}>
                      Review cleaning plan
                      <ArrowRight size={16} />
                    </Button>
                  </div>
                  {uploaded.metadata.header_adjustments.length > 0 && (
                    <div className="notice">
                      Duplicate or empty headers were assigned unique names:{" "}
                      {uploaded.metadata.header_adjustments
                        .map((h) => `${h.original} → ${h.name}`)
                        .join(", ")}
                    </div>
                  )}
                  <Button variant="outline" onClick={() => setStage("editor")}>
                    Open interactive spreadsheet
                  </Button>
                  <p>
                    Apply basic cleanup to a copy, then review and fix colored
                    issues directly in the sheet.
                  </p>
                  <ColumnAnalysis columns={profile.columns} />
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>Spreadsheet preview</h2>
                      <span className="tag">ORIGINAL DATA</span>
                    </div>
                    <DataTable
                      data={uploaded.preview}
                      onPage={paginate}
                      disabled={busy}
                    />
                  </section>
                </>
              )}
              {stage === "configure" && (
                <>
                  <div className="dashboard-actions">
                    <div>
                      <h2>Your cleaning plan</h2>
                      <p>
                        {operations.filter((o) => o.enabled).length} of{" "}
                        {operations.length} operations selected. Review and
                        destructive actions start disabled.
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => setStage("profile")}
                    >
                      Back to analysis
                    </Button>
                  </div>
                  <div className="notice">
                    <ShieldCheck size={18} />
                    Your original file is preserved. Invalid and ambiguous
                    values remain unchanged unless explicitly resolved.
                  </div>
                  <PlanSelection
                    operations={operations}
                    disabled={busy}
                    onSelect={(enabled) => {
                      setOperations((items) =>
                        items.map((o) => ({
                          ...o,
                          enabled,
                          parameters:
                            o.operation === "impute_missing_values"
                              ? { ...o.parameters, confirmed: false }
                              : o.parameters,
                        })),
                      );
                      setComparison(null);
                    }}
                  />
                  <div className="column-operation-groups">
                    {operationGroups.map((group) => (
                      <section
                        key={group.column || "dataset"}
                        className="column-operation-group"
                        aria-label={
                          group.column
                            ? `Cleaning actions for column ${group.column}`
                            : "Dataset cleaning actions"
                        }
                      >
                        <div className="column-section-heading">
                          <div>
                            <span className="column-caption">
                              {group.column ? "COLUMN" : "DATASET"}
                            </span>
                            <h3>{group.column || "Entire dataset"}</h3>
                          </div>
                          <span className="type-tag">
                            {group.operations.length} cleaning actions
                          </span>
                        </div>
                        <div className="operation-list">
                          {group.operations.map((o) => (
                            <section
                              key={o.id}
                              className={`operation ${o.enabled ? "selected" : ""}`}
                            >
                              <label className="operation-check">
                                <input
                                  type="checkbox"
                                  checked={o.enabled}
                                  disabled={busy}
                                  onChange={(e) =>
                                    update(o.id, { enabled: e.target.checked })
                                  }
                                />
                                <span className="operation-icon">
                                  <WandSparkles size={18} />
                                </span>
                                <span>
                                  <strong>{label(o.operation)}</strong>
                                  <small>
                                    {o.column || "Entire dataset"} · up to{" "}
                                    {o.affected_rows} rows
                                  </small>
                                </span>
                              </label>
                              <span className={`safety ${o.safety}`}>
                                {o.safety === "safe"
                                  ? "Safe suggestion"
                                  : o.safety === "review"
                                    ? "Review required"
                                    : "Removes rows"}
                              </span>
                              <p>{o.explanation}</p>
                              {o.operation === "impute_missing_values" &&
                                uploaded && (
                                  <ImputationControls
                                    operation={o}
                                    columns={uploaded.profile.columns}
                                    disabled={busy}
                                    onChange={(parameters) =>
                                      update(o.id, { parameters })
                                    }
                                  />
                                )}
                              {o.operation === "resolve_invalid_dates" &&
                                uploaded && (
                                  <InvalidDateControls
                                    fileId={uploaded.file_id}
                                    operation={o}
                                    disabled={busy}
                                    onChange={(parameters) =>
                                      update(o.id, { parameters })
                                    }
                                  />
                                )}
                              {o.operation === "normalize_phone" && (
                                <PhoneControls
                                  operation={o}
                                  disabled={busy}
                                  onChange={(parameters) =>
                                    update(o.id, { parameters })
                                  }
                                />
                              )}
                              {o.operation === "normalize_symbols" && (
                                <SymbolControls
                                  operation={o}
                                  disabled={busy}
                                  onChange={(parameters) =>
                                    update(o.id, { parameters })
                                  }
                                />
                              )}
                              {o.operation === "normalize_percentage" && (
                                <PercentageControls
                                  operation={o}
                                  disabled={busy}
                                  onChange={(parameters) =>
                                    update(o.id, { parameters })
                                  }
                                />
                              )}
                              {o.operation === "normalize_currency" && (
                                <CurrencyControls
                                  operation={o}
                                  disabled={busy}
                                  onChange={(parameters) =>
                                    update(o.id, { parameters })
                                  }
                                />
                              )}
                              {o.operation === "normalize_dates" && (
                                <label className="setting">
                                  Ambiguous date interpretation
                                  <select
                                    aria-label={`Date interpretation for ${o.column}`}
                                    value={String(o.parameters.interpretation)}
                                    onChange={(e) =>
                                      update(o.id, {
                                        parameters: {
                                          ...o.parameters,
                                          interpretation: e.target.value,
                                        },
                                      })
                                    }
                                  >
                                    <option value="preserve">
                                      Preserve ambiguous values
                                    </option>
                                    <option value="day_first">
                                      I confirm day / month / year
                                    </option>
                                    <option value="month_first">
                                      I confirm month / day / year
                                    </option>
                                  </select>
                                </label>
                              )}
                              {o.operation === "normalize_capitalization" && (
                                <label className="setting">
                                  Capitalization
                                  <select
                                    aria-label={`Capitalization for ${o.column}`}
                                    value={String(o.parameters.strategy)}
                                    onChange={(e) =>
                                      update(o.id, {
                                        parameters: {
                                          strategy: e.target.value,
                                        },
                                      })
                                    }
                                  >
                                    {["title", "lower", "upper"].map((v) => (
                                      <option key={v}>{v}</option>
                                    ))}
                                  </select>
                                </label>
                              )}
                              {o.operation === "normalize_missing_values" && (
                                <label className="setting">
                                  Missing markers (comma-separated)
                                  <input
                                    aria-label={`Missing markers for ${o.column}`}
                                    value={(
                                      o.parameters.markers as string[]
                                    ).join(",")}
                                    onChange={(e) =>
                                      update(o.id, {
                                        parameters: {
                                          markers: e.target.value.split(","),
                                        },
                                      })
                                    }
                                  />
                                </label>
                              )}
                              {o.operation === "remove_duplicates" && (
                                <label className="setting">
                                  Duplicate columns
                                  <select
                                    aria-label="Duplicate columns"
                                    value={
                                      o.parameters.subset
                                        ? String(
                                            (
                                              o.parameters.subset as string[]
                                            )[0],
                                          )
                                        : ""
                                    }
                                    onChange={(e) =>
                                      update(o.id, {
                                        parameters: {
                                          subset: e.target.value
                                            ? [e.target.value]
                                            : null,
                                        },
                                      })
                                    }
                                  >
                                    <option value="">
                                      All columns (complete rows)
                                    </option>
                                    {uploaded?.preview.columns.map((c) => (
                                      <option key={c}>{c}</option>
                                    ))}
                                  </select>
                                </label>
                              )}
                            </section>
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                  {operations.length === 0 && (
                    <div className="panel empty-state">
                      <CheckCheck />
                      <h3>No suggested transformations</h3>
                      <p>
                        You can still export this spreadsheet or rename a column
                        below.
                      </p>
                    </div>
                  )}
                  <section className="rename-panel">
                    <h3>Rename a column</h3>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const form = new FormData(e.currentTarget);
                        const column = String(form.get("column")),
                          name = String(form.get("name")).trim();
                        if (name) {
                          setComparison(null);
                          setOperations((items) => [
                            ...items.map((o) =>
                              o.operation === "impute_missing_values"
                                ? {
                                    ...o,
                                    parameters: {
                                      ...o.parameters,
                                      confirmed: false,
                                    },
                                  }
                                : o,
                            ),
                            {
                              id: `rename-${Date.now()}`,
                              column,
                              operation: "rename_column",
                              parameters: { name },
                              enabled: true,
                              affected_rows: 1,
                              explanation: `Rename “${column}” to “${name}”.`,
                              issue: "column_name",
                              safety: "review",
                              requires_confirmation: true,
                            },
                          ]);
                        }
                        e.currentTarget.reset();
                      }}
                    >
                      <select aria-label="Column to rename" name="column">
                        {uploaded?.preview.columns.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                      <input
                        aria-label="New column name"
                        name="name"
                        placeholder="New column name"
                        required
                      />
                      <Button type="submit" variant="outline" size="sm">
                        Add rename
                      </Button>
                    </form>
                  </section>
                  <div className="apply-bar">
                    <span>
                      {operations.filter((o) => o.enabled).length} approved
                      operations
                    </span>
                    <div>
                      <Button
                        variant="outline"
                        onClick={preview}
                        disabled={busy}
                      >
                        {busy ? (
                          <Loader2 className="spin" size={16} />
                        ) : (
                          <SearchCheck size={16} />
                        )}
                        Preview changes
                      </Button>
                      <Button
                        onClick={clean}
                        disabled={
                          busy ||
                          operations.some(
                            (o) =>
                              o.enabled &&
                              o.operation === "impute_missing_values" &&
                              o.parameters.method !== "preserve" &&
                              (!comparison || o.parameters.confirmed !== true),
                          )
                        }
                      >
                        {busy ? (
                          <Loader2 className="spin" size={16} />
                        ) : (
                          <WandSparkles size={16} />
                        )}
                        Apply cleaning
                      </Button>
                    </div>
                  </div>
                  {comparison && (
                    <>
                      <ImputationAudit operations={comparison.operations} />
                      {operations
                        .filter(
                          (o) =>
                            o.enabled &&
                            o.operation === "impute_missing_values" &&
                            o.parameters.method !== "preserve",
                        )
                        .map((o) => (
                          <label
                            className="assumption-check imputation-approval"
                            key={o.id}
                          >
                            <input
                              type="checkbox"
                              disabled={busy}
                              aria-label={`Confirm imputation for ${o.column}`}
                              checked={o.parameters.confirmed === true}
                              onChange={(e) =>
                                setOperations((items) =>
                                  items.map((item) =>
                                    item.id === o.id
                                      ? {
                                          ...item,
                                          parameters: {
                                            ...item.parameters,
                                            confirmed: e.target.checked,
                                          },
                                        }
                                      : item,
                                  ),
                                )
                              }
                            />
                            I reviewed the preview for {o.column} and approve
                            filling missing cells with estimates or
                            placeholders.
                          </label>
                        ))}
                    </>
                  )}
                  {comparison && (
                    <div className="comparison">
                      <section className="panel">
                        <div className="panel-heading">
                          <h2>Before</h2>
                        </div>
                        <DataTable data={comparison.before} />
                      </section>
                      <section className="panel">
                        <div className="panel-heading">
                          <h2>After (preview)</h2>
                        </div>
                        <DataTable data={comparison.after} />
                      </section>
                    </div>
                  )}
                </>
              )}
              {stage === "results" && results && (
                <>
                  <div className="success-banner">
                    <span>
                      <CheckCheck size={24} />
                    </span>
                    <div>
                      <h2>Cleaning complete</h2>
                      <p>
                        {results.validation.modified_values} changes logged.{" "}
                        {results.validation.unresolved_issues} issue categories
                        remain — review them below.
                      </p>
                    </div>
                  </div>
                  <Stats
                    values={[
                      [
                        "Rows before → after",
                        `${results.validation.rows_before} → ${results.validation.rows_after}`,
                      ],
                      ["Values modified", results.validation.modified_values],
                      [
                        "Duplicates removed",
                        results.validation.duplicates_removed,
                      ],
                      [
                        "Issues remaining",
                        results.validation.unresolved_issues,
                      ],
                    ]}
                  />
                  <div className="download-bar">
                    <div>
                      <h2>Ready to take it from here?</h2>
                      <p>
                        Export your cleaned spreadsheet and its transformation
                        report.
                      </p>
                    </div>
                    <div>
                      <a
                        className="button outline"
                        href={`/api/jobs/${job}/download?format=report`}
                        download
                      >
                        <Download size={16} />
                        Report
                      </a>
                      <a
                        className="button outline"
                        href={`/api/jobs/${job}/download?format=xlsx`}
                        download
                      >
                        <Download size={16} />
                        Download XLSX
                      </a>
                      <a
                        className="button primary"
                        href={`/api/jobs/${job}/download?format=csv`}
                        download
                      >
                        <Download size={16} />
                        Download CSV
                      </a>
                    </div>
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>Cleaned spreadsheet</h2>
                      <span className="tag">CLEANED COPY</span>
                    </div>
                    <DataTable
                      data={results.preview}
                      onPage={paginate}
                      disabled={busy}
                    />
                  </section>
                  <ImputationAudit operations={results.operations} />
                  <div className="result-grid">
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Transformation log</h2>
                      </div>
                      <div className="panel-body">
                        {results.operations.length === 0 ? (
                          <p>No transformations selected.</p>
                        ) : (
                          results.operations.map((o, i) => (
                            <div className="log-row" key={i}>
                              <Check size={16} />
                              <div>
                                <strong>{label(o.operation)}</strong>
                                <small>
                                  {o.column || "Entire dataset"} ·{" "}
                                  {o.operation === "remove_duplicates"
                                    ? `${o.removed_rows} rows removed`
                                    : o.operation === "rename_column"
                                      ? `renamed to ${String(o.parameters.name)}`
                                      : `${o.modified_values} values modified`}
                                </small>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Still worth a look</h2>
                        <span className="count-badge">
                          {results.validation.unresolved_issues}
                        </span>
                      </div>
                      <div className="panel-body">
                        <ColumnAnalysis
                          columns={results.validation.after.columns}
                          compact
                        />
                        {results.validation.after.duplicate_rows > 0 && (
                          <div className="remaining-issue">
                            {results.validation.after.duplicate_rows} duplicate
                            rows remain.
                          </div>
                        )}
                        {results.validation.unresolved_issues === 0 && (
                          <p>No issues detected by the current checks.</p>
                        )}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setStage("configure");
                            setComparison(null);
                          }}
                        >
                          Revise cleaning plan
                        </Button>
                      </div>
                    </section>
                  </div>
                </>
              )}
            </>
          )}
          <section
            id="privacy"
            className="column-card"
            aria-labelledby="privacy-heading"
          >
            <h2 id="privacy-heading">Privacy policy</h2>
            <p>
              Your spreadsheets are used only to analyze, preview, clean, and
              export the changes you request. DataNeat does not sell or share
              spreadsheet contents with third parties, use them for advertising
              or AI training, or send them to external AI services.
            </p>
            <p>
              Processing takes place on the server running DataNeat. When you
              run it locally, that server is your computer. On a hosted website,
              uploads are stored on the hosting server, where its operator
              controls infrastructure access and backups.
            </p>
            <p>
              Files are restricted to your browser session. A session cookie is
              used for this access; no advertising or tracking cookies are used.
              Files become inaccessible after 24 hours and expired files are
              removed during cleanup. You can use Delete file to remove the
              active file and its associated results sooner.
            </p>
            <p>
              This policy describes the current application. Any future
              third-party integrations or changes in data use must be disclosed
              before use.
            </p>
          </section>
          <footer>
            <span>
              <Layers3 size={15} />
              DataNeat <span className="footer-divider">/</span> Make room for
              better data.
            </span>
            <span id="help">
              Private session · Files expire in 24 hours · CSV / XLSX
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
function Feature({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <section className="feature-card">
      <span className="feature-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{text}</p>
    </section>
  );
}
function Stats({ values }: { values: [string, string | number][] }) {
  return (
    <div className="stats">
      {values.map(([name, value]) => (
        <div className="stat" key={name}>
          <span>{name}</span>
          <strong>
            {typeof value === "number" ? value.toLocaleString() : value}
          </strong>
        </div>
      ))}
    </div>
  );
}

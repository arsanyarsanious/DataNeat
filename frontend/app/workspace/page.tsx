"use client";
import { useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronRight,
  CircleHelp,
  Download,
  FileSpreadsheet,
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
import { CleaningProgress } from "@/components/cleaning-progress";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { DataNeatMark } from "@/components/dataneat-mark";
import { AccountFileControls, type FileStorageStatus } from "@/components/account-file-controls";
import { api, initializeSession, type Upload } from "@/lib/types";
type WorkbookInspection = {
  filename: string;
  sheets: {name:string;rows:number;columns:number;hidden:boolean;selectable:boolean;reason?:string}[];
  limits: {max_rows:number;max_columns:number;max_sheets:number};
  selected_sheet: string | null;
};
export default function Home() {
  const [flowPhase,setFlowPhase]=useState<"choose"|"clean"|"results">("choose");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [stage, setStage] = useState<
    "upload" | "editor"
  >("upload");
  const [uploaded, setUploaded] = useState<Upload | null>(null);
  const [storageStatus,setStorageStatus]=useState<FileStorageStatus|null>(null),[confirmDelete,setConfirmDelete]=useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false), [restoring, setRestoring] = useState(true);
  const [progress, setProgress] = useState(0), [error, setError] = useState("");
  const [drag, setDrag] = useState(false), [dark, setDark] = useState(false);
  const [uploadLimit, setUploadLimit] = useState(20);
  const [tableLimits, setTableLimits] = useState({ rows: 100000, columns: 200 });
  const [inspecting, setInspecting] = useState(false);
  const [pendingWorkbook, setPendingWorkbook] = useState<{file:File;inspection:WorkbookInspection}|null>(null);
  const [selectedWorksheet, setSelectedWorksheet] = useState("");
  const sheetDialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const dialog = sheetDialog.current;
    if (pendingWorkbook && dialog && !dialog.open) dialog.showModal();
    return () => { if(dialog?.open) dialog.close(); };
  }, [pendingWorkbook]);
  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        const requested = new URLSearchParams(window.location.search).get("file");
        if(requested&&!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(requested))throw new Error("Invalid file reference");
        const raw = sessionStorage.getItem("dataneat-workspace");
        if (!raw&&!requested) return;
        const saved = requested?{fileId:requested}:JSON.parse(raw!);
        if (typeof saved.fileId !== "string") return;
        const data = await api<Upload>(`/files/${saved.fileId}/workspace`);
        if (!active) return;
        setUploaded(data);
        setStorageStatus(data.storage||null);
        if (raw && (saved.interactive === false || saved.job)) sessionStorage.setItem("dataneat-legacy-workspace", raw);
        setStage("editor");
      } catch {
        sessionStorage.removeItem("dataneat-workspace");
        if (active) setError("This file has expired, was deleted, or belongs to another account. Open My files or upload it again.");
      } finally { if (active) setRestoring(false); }
    }
    void restore();
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!uploaded || restoring) return;
    try { sessionStorage.setItem("dataneat-workspace", JSON.stringify({ fileId: uploaded.file_id, stage, interactive: true })); } catch { /* Browser storage may be unavailable. */ }
  }, [uploaded, restoring, stage]);
  useEffect(() => {
    setSidebarCollapsed(localStorage.getItem("dataneat-sidebar-collapsed") === "true");
    void initializeSession()
      .then((data) => { setUploadLimit(data.max_upload_mb); setTableLimits({ rows: data.max_rows || 100000, columns: data.max_columns || 200 }); })
      .catch(() => {});
    const value = localStorage.getItem("dataneat-theme") === "dark";
    setDark(value);
    document.documentElement.classList.toggle("dark", value);
  }, []);
  function theme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("dataneat-theme", next ? "dark" : "light");
  }
  function validFile(selected: File) {
    if (restoring) return;
    if (!/\.(csv|xlsx)$/i.test(selected.name)) {
      setError("Choose a CSV or XLSX spreadsheet.");
      return false;
    }
    if (selected.size > uploadLimit * 1024 * 1024) {
      setError(`This file exceeds the ${uploadLimit} MB upload limit.`);
      return false;
    }
    return true;
  }
  async function selectFile(selected: File) {
    if (!validFile(selected) || busy) return;
    if (/\.csv$/i.test(selected.name)) { await upload(selected); return; }
    setBusy(true);setInspecting(true);setError("");
    try {
      await initializeSession();
      const form = new FormData();form.append("file",selected);
      const inspection = await api<WorkbookInspection>("/files/inspect-workbook",{method:"POST",body:form});
      setSelectedWorksheet("");setPendingWorkbook({file:selected,inspection});
    } catch(e) { setError((e as Error).message); }
    finally { setBusy(false);setInspecting(false); }
  }
  async function upload(selected: File, sheet?: string, confirmed=false) {
    if (!validFile(selected)) return;
    if(uploaded&&!confirmed&&!window.dispatchEvent(new CustomEvent("dataneat-before-reset",{cancelable:true,detail:{proceed:()=>void upload(selected,sheet,true)}})))return;
    setBusy(true);
    setError("");
    setProgress(0);
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
      // The successful new workspace must still open if an older temporary file has expired.
      if (uploaded)
        void api(`/files/${uploaded.file_id}?only_temporary=true`, { method: "DELETE" }).catch(()=>{});
      setUploaded(response);
      setStorageStatus(response.storage||null);setConfirmDelete(false);window.history.replaceState({},"","/workspace");
      setFile(selected);
      setFlowPhase("choose");
      setStage("editor");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reset(confirmed=false,deleteFile=false) {
    if(!confirmed&&!deleteFile&&!window.dispatchEvent(new CustomEvent("dataneat-before-reset",{cancelable:true,detail:{proceed:()=>void reset(true,deleteFile)}})))return;
    sessionStorage.removeItem("dataneat-workspace");
    setError("");
    setBusy(true);
    try {
      if (uploaded)
        await api(`/files/${uploaded.file_id}${deleteFile?"":"?only_temporary=true"}`, { method: "DELETE" });
      setUploaded(null);
        setStorageStatus(null);setConfirmDelete(false);window.history.replaceState({},"","/workspace");
        setFile(null);
        setStage("upload");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}${stage==="editor"?" workspace-focused":""}`}>
      <WorkspaceSidebar collapsed={sidebarCollapsed} dark={dark} onTheme={theme} onToggle={() => {
        const next = !sidebarCollapsed;
        setSidebarCollapsed(next);
        localStorage.setItem("dataneat-sidebar-collapsed", String(next));
      }} onCleaner={() => setStage(uploaded ? "editor" : "upload")} />
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
          {restoring && <CleaningProgress label="Restoring your workspace…" />}
          {busy && uploaded && <CleaningProgress label={inspecting?"Reading worksheet names…":"Processing your spreadsheet…"} />}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span />
                LESS MESS. MORE POSSIBILITY.
              </div>
              <h1>
                {stage === "upload" ? "Good data starts here." : flowPhase==="choose" ? "Explore your data." : flowPhase==="results" ? "Export your results." : "Your spreadsheet."}
              </h1>
              <p>
                {stage === "upload" ? "Turn messy spreadsheets into clean, consistent data — without the busywork." : ""}
              </p>
            </div>
            {uploaded && (
              <Button variant="outline" onClick={()=>void reset()} disabled={busy}>
                <Plus size={16} />
                New spreadsheet
              </Button>
            )}
          </div>
          <div className="stepper" hidden={stage!=="upload"}>
            {(["upload", "profile", "configure", "results"] as const).map(
              (item, i) => {
                const index = stage === "upload" ? 0 : 2;
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
                          "Upload",
                          "Explore",
                          "Review",
                          "Export",
                        ][i]
                      }
                    </span>
                    {i < 3 && <div className="step-line" />}
                  </div>
                );
              },
            )}
          </div>
          {pendingWorkbook && <dialog ref={sheetDialog} className="workbook-dialog" aria-labelledby="workbook-title" aria-describedby="workbook-description" onCancel={()=>setPendingWorkbook(null)}>
            <div className="workbook-dialog-heading"><span className="heading-icon"><FileSpreadsheet size={24}/></span><div><h2 id="workbook-title">Choose a worksheet</h2><p>{pendingWorkbook.inspection.filename}</p></div><button className="icon-button" aria-label="Close worksheet selection" onClick={()=>setPendingWorkbook(null)}><X size={20}/></button></div>
            <p id="workbook-description">Clean one worksheet at a time. Choose the sheet you want to analyze.</p>
            <fieldset className="workbook-options"><legend className="sr-only">Worksheets in this workbook</legend>{pendingWorkbook.inspection.sheets.map(s=><label key={s.name} className={`workbook-option${selectedWorksheet===s.name?" selected":""}${!s.selectable?" unavailable":""}`}><input type="radio" name="worksheet" value={s.name} checked={selectedWorksheet===s.name} disabled={!s.selectable} onChange={()=>setSelectedWorksheet(s.name)}/><span><strong>{s.name}{s.hidden&&<small className="worksheet-hidden">Hidden</small>}</strong><small>{s.selectable?`${s.rows.toLocaleString()} data rows · ${s.columns.toLocaleString()} columns (reported bounds)`:s.reason||"This worksheet cannot be analyzed."}</small></span></label>)}</fieldset>
            <div className="workbook-scope-note"><ShieldCheck size={19}/><p><strong>Only the selected sheet is cleaned and exported.</strong> Other sheets stay in your original workbook. Export creates a data table; workbook formatting, charts and executable formulas are not preserved.</p></div>
            {!pendingWorkbook.inspection.sheets.some(s=>s.selectable)&&<p className="error" role="alert">No selectable worksheet. Use a sheet with a header and at least one data row, within {pendingWorkbook.inspection.limits.max_rows.toLocaleString()} rows and {pendingWorkbook.inspection.limits.max_columns} columns.</p>}
            <div className="workbook-dialog-footer"><Button variant="outline" onClick={()=>setPendingWorkbook(null)}>Cancel</Button><Button disabled={!selectedWorksheet} onClick={()=>{const source=pendingWorkbook.file;const sheet=selectedWorksheet;setPendingWorkbook(null);void upload(source,sheet);}}>Analyze selected sheet<ChevronRight size={17}/></Button></div>
          </dialog>}
          {error && (
            <div className="error" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
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
                      void selectFile(e.dataTransfer.files[0]);
                  }}
                >
                  <div className="upload-grid-art" aria-hidden="true">
                    <div className="upload-mini-grid">{Array.from({length:24},(_,i)=><span key={i}/>)}</div>
                    <span className="upload-cloud-badge"><UploadCloud size={38} strokeWidth={1.5}/></span>
                  </div>
                  <h3>
                    {busy
                      ? inspecting?"Reading your workbook…":"Analyzing your spreadsheet…"
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
                      if (selected) void selectFile(selected);
                      e.target.value = "";
                    }}
                  />
                  <span className="file-hint">
                    CSV or XLSX <span>·</span> Up to {uploadLimit} MB
                    <span>·</span> {tableLimits.rows.toLocaleString()} rows / {tableLimits.columns} columns
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
                          : inspecting?"Reading worksheet names…"
                          : `${progress}% uploaded`}
                      </span>
                    </div>
                  )}
                </div>
                <div className="upload-note">
                  <ShieldCheck size={16} />
                  <span>
                    Original file preserved. Your data summary appears after upload.
                  </span>
                </div>
                <details className="upload-details"><summary>Privacy & Excel worksheet limits</summary><p>Your files are private and never used for training. Temporary files expire after 24 hours unless you save them to your signed-in account. XLSX files: choose one worksheet before analysis; export includes only that sheet as a data table, without workbook formatting, charts or executable formulas. Keep your original workbook.</p></details>
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
                    <div className="selected-worksheet"><span>Worksheet <strong>{uploaded.metadata.worksheet}</strong> · 1 of {uploaded.metadata.sheets.length}</span><small>Only this sheet is cleaned and exported.</small>{file?<button className="worksheet-switch" disabled={busy} onClick={()=>void selectFile(file)}>Choose another worksheet</button>:<small>Upload the original workbook to choose another sheet.</small>}</div>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={()=>storageStatus?.saved?setConfirmDelete(true):void reset(false,true)}
                    disabled={busy}
                  >
                    <Trash2 size={15} />
                    Delete file
                  </Button>
                </div>
              )}
              {stage === "editor" && uploaded && (
                <>
                  <AccountFileControls fileId={uploaded.file_id} disabled={busy} onChange={setStorageStatus}/>
                  {confirmDelete&&<div className="account-file-delete-confirm" role="group" aria-label="Delete saved spreadsheet"><p>Delete this saved file, original data and cleaning history from your account? This cannot be undone.</p><div><Button variant="outline" onClick={()=>setConfirmDelete(false)}>Keep file</Button><Button onClick={()=>void reset(true,true)}>Delete permanently</Button></div></div>}
                  {uploaded.metadata.formula_notice&&<p className="original-colors-note">{uploaded.metadata.formula_notice}</p>}
                  <InteractiveSheet key={uploaded.file_id} fileId={uploaded.file_id} originalRows={uploaded.profile.rows} persisted={storageStatus?.saved??uploaded.storage?.saved??false} onPhaseChange={setFlowPhase} />
                </>
              )}
            </>
          )}
          <footer>
            <span>
              <DataNeatMark size={18} />
              DataNeat <span className="footer-divider">/</span> Make room for
              better data.
            </span>
            <span id="help">
              {storageStatus?.saved?"Saved to your account · No automatic expiry":"Temporary files · 24-hour expiry"} · CSV / XLSX
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

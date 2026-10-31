"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Profile } from "@/lib/types";
import { workflowJob, type WorkflowStatus } from "@/lib/workflow";
import { DATE_FORMAT_OPTIONS } from "@/lib/date-formats";
import { compatibleReusableChoice, deleteReusableChoice, readReusableChoices, sanitizeReusableDecisions, saveReusableChoice, type CleaningDecision, type ReusableChoice } from "@/lib/reusable-cleaning";
import { Button } from "./ui/button";

type SuggestedGroup = { id: string; label: string; description: string; safety: string; steps: CleaningDecision[]; columns: string[]; count: number };
type Suggested = { revision: number; groups: SuggestedGroup[]; deferred: { kind: string; label: string; count: number; reason: string }[]; source_columns: string[]; protected_columns?: string[] };
type Entry = { action: string; column: string; changed_cells: number; interpreted_dates?: number; examples?: { row_index?: number; spreadsheet_row?: number; before: unknown; after: unknown }[]; warnings?: string[] };
type Review = { operations: Entry[]; changed_cells: number; removed_rows?: number; revision?: number };
type Props = { fileId: string; revision: number; profile: Profile; initialTab?: "suggested" | "saved"; onClose: () => void; onApplied: () => Promise<void>; onBusyChange?: (value: boolean) => void; onGuided?: () => void; onFinish?: () => void };
const actionLabels: Record<string, string> = { trim_whitespace: "Trim extra whitespace", normalize_boolean: "Unify boolean labels", normalize_capitalization: "Unify capitalization", normalize_dates: "Standardize date format", normalize_time: "Standardize clock time", normalize_duration: "Standardize elapsed durations" };
const text = (value: unknown) => value === null || value === undefined || value === "" ? "empty" : String(value);

export function QuickCleanReview({ fileId, revision, profile, initialTab = "suggested", onClose, onApplied, onBusyChange, onGuided, onFinish }: Props) {
  const [tab, setTab] = useState(initialTab), [suggested, setSuggested] = useState<Suggested | null>(null), [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string[]>([]), [excluded, setExcluded] = useState<Record<string, string[]>>({});
  const [overrides, setOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const [identifiers, setIdentifiers] = useState<string[]>([]), [saved, setSaved] = useState<ReusableChoice[]>([]), [activeSaved, setActiveSaved] = useState("");
  const [protectedColumns, setProtectedColumns] = useState<string[]>([]);
  const [savedSteps, setSavedSteps] = useState<CleaningDecision[]>([]), [savedWarnings, setSavedWarnings] = useState<string[]>([]), [choiceName, setChoiceName] = useState("");
  const [review, setReview] = useState<Review | null>(null), [reviewSignature, setReviewSignature] = useState(""), [reviewRevision, setReviewRevision] = useState<number | null>(null);
  const [applied, setApplied] = useState<Review | null>(null), [busy, setBusy] = useState(false), [job, setJob] = useState<WorkflowStatus | null>(null);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const panel = useRef<HTMLDivElement>(null), alert = useRef<HTMLDivElement>(null), close = useRef<HTMLButtonElement>(null);
  const callback = useRef(onBusyChange); callback.current = onBusyChange;
  useEffect(() => { callback.current?.(busy); return () => callback.current?.(false); }, [busy]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null, overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden"; close.current?.focus();
    const stored = readReusableChoices(); setSaved(stored.choices); setNotice(stored.warning);
    return () => { document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setReview(null); setReviewSignature("");
    void Promise.all([
      api<Suggested>(`/files/${fileId}/workflow/suggested`, { signal: controller.signal }),
      api<{ rules: Record<string, { type?: string }>; protected_columns?: string[] }>(`/files/${fileId}/workflow/settings`, { signal: controller.signal }),
    ]).then(([result, settings]) => {
      if (controller.signal.aborted) return;
      if (result.revision !== revision) throw new Error("Your spreadsheet changed. Close this window and reopen it to review the current copy.");
      setSuggested(result); setIdentifiers(Object.entries(settings.rules || {}).filter(([, rule]) => rule.type === "identifier").map(([name]) => name));
      setProtectedColumns(result.protected_columns || settings.protected_columns || []);
      setSelected(result.groups.filter(group => group.safety === "safe").map(group => group.id)); setExcluded({}); setOverrides({});
    }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [fileId, revision]);
  useEffect(() => {
    const listen = (event: Event) => { const detail = (event as CustomEvent).detail; if (detail.fileId === fileId) setJob(detail.status); };
    window.addEventListener("dataneat-workflow-job", listen); return () => window.removeEventListener("dataneat-workflow-job", listen);
  }, [fileId]);
  useEffect(() => { if (error) alert.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [error]);

  const groups = suggested?.groups || [];
  const steps = useMemo(() => tab === "saved" ? savedSteps : groups.filter(group => selected.includes(group.id)).flatMap(group => group.steps.filter(step => !(excluded[group.id] || []).includes(step.body.column)).map(step => ({ ...step, body: { ...step.body, parameters: { ...step.body.parameters, ...overrides[group.id] } } }))), [tab, savedSteps, groups, selected, excluded, overrides]);
  const signature = JSON.stringify(steps);
  const canApply = !!review && reviewSignature === signature && reviewRevision === revision && (review.changed_cells > 0 || (review.removed_rows || 0) > 0 || review.operations.some(entry => (entry.interpreted_dates || 0) > 0));
  useEffect(() => {
    if (loading || !activeSaved) return;
    const choice = saved.find(item => item.id === activeSaved);
    if (!choice) return;
    const compatible = compatibleReusableChoice(choice, profile, identifiers, protectedColumns);
    setSavedSteps(compatible.steps); setSavedWarnings(compatible.warnings);
    setReview(null); setReviewSignature("");
  }, [loading, activeSaved, saved, profile, identifiers, protectedColumns]);
  function invalidate() { setReview(null); setReviewSignature(""); setError(""); setNotice(""); }
  function switchTab(value: "suggested" | "saved") { setTab(value); invalidate(); }
  function parameter(group: SuggestedGroup, key: string, value: unknown) { setOverrides(current => ({ ...current, [group.id]: { ...current[group.id], [key]: value } })); invalidate(); }
  function loadChoice(choice: ReusableChoice) {
    const compatible = compatibleReusableChoice(choice, profile, identifiers, protectedColumns);
    setActiveSaved(choice.id); setChoiceName(choice.name); setSavedSteps(compatible.steps); setSavedWarnings(compatible.warnings); invalidate();
    setNotice(`${compatible.steps.length} compatible actions loaded. ${compatible.skipped ? `${compatible.skipped} incompatible actions were skipped. ` : ""}Preview these choices on the current file before applying.`);
  }
  async function run(apply = false) {
    if (!steps.length) { setError("Choose at least one fix to preview."); return; }
    if (steps.length > 100) { setError("A review can contain up to 100 column actions. Deselect some columns, then review the remaining fixes in another run."); return; }
    if (apply && !canApply) { setError("Preview the current choices before applying them."); return; }
    setBusy(true); setError(""); setNotice(""); setJob(null);
    const startedSignature = signature, startedRevision = revision;
    try {
      const result = await workflowJob<Review>(fileId, startedRevision, { operation: apply ? "plan" : "plan_preview", steps: steps.map(step => ({ ...step, body: { ...step.body, revision: startedRevision, row_index: 0, confirmed: true } })) });
      if (apply) {
        setApplied(result); setReview(null);
        try { await onApplied(); } catch { setError("Your reviewed fixes were applied, but the sheet could not refresh. Close this window and reload the workspace to see the committed changes."); }
      } else { setReview(result); setReviewSignature(startedSignature); setReviewRevision(startedRevision); }
    } catch (reason) { setError((reason as Error).message); setReview(null); }
    finally { setBusy(false); }
  }
  function save() {
    try { setSaved(saveReusableChoice(choiceName, steps, suggested?.source_columns || profile.columns.map(column => column.column_name))); setNotice("Choices saved in this browser. Only action settings and column names were saved; cell values were excluded."); setError(""); }
    catch (reason) { setError((reason as Error).message); }
  }
  async function cancel() {
    try { const id = job?.id || sessionStorage.getItem(`dataneat-job-${fileId}`); if (!id) return; await api(`/workflow-jobs/${id}/cancel`, { method: "POST" }); setNotice("Cancellation requested. Waiting for the current operation to stop."); } catch (reason) { setError((reason as Error).message); }
  }
  const currentSaved = saved.find(choice => choice.id === activeSaved);

  return <div className="simplify-backdrop"><div className="simplify-dialog quick-clean-dialog" role="dialog" aria-modal="true" aria-labelledby="quick-clean-title" ref={panel} tabIndex={-1} onKeyDown={event => {
    if (event.key === "Escape") { event.stopPropagation(); event.preventDefault(); if (!busy) onClose(); }
    if (event.key === "Tab") {
      const controls = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],summary,[tabindex="0"]') || []).filter(element => element.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  }}>
    <header className="simplify-heading"><div><span className="simplify-eyebrow">One review, one application</span><h2 id="quick-clean-title">Quick cleaning</h2></div><button type="button" className="button outline" ref={close} disabled={busy} onClick={onClose}>Close</button></header>
    <div className="simplify-body">
      {applied ? <section className="quick-clean-complete" aria-label="Quick cleaning complete"><h3>Reviewed fixes applied</h3><p role="status">{applied.operations.length.toLocaleString()} recorded steps · {applied.changed_cells.toLocaleString()} cell changes{applied.removed_rows ? ` · ${applied.removed_rows.toLocaleString()} rows removed` : ""}.</p><p>Your current spreadsheet includes these changes. Each step is available in Cleaning history.</p><details><summary>See what changed</summary><ul>{applied.operations.map((entry, index) => <li key={index}>{entry.column} · {actionLabels[entry.action] || entry.action} · {entry.changed_cells.toLocaleString()} changes</li>)}</ul></details><div className="simplify-actions">{onGuided && <Button onClick={onGuided}>Review remaining issues</Button>}{onFinish && <Button variant="outline" onClick={onFinish}>Review &amp; export</Button>}<Button variant="ghost" onClick={onClose}>Return to spreadsheet</Button></div></section> : <>
        <p className="simplify-intro">Choose fixes once for the relevant columns, review their combined effect, then apply them together. Your current sheet changes only when you apply the reviewed fixes.</p>
        <nav className="simplify-tabs" aria-label="Quick cleaning choices"><button type="button" disabled={busy} aria-pressed={tab === "suggested"} onClick={() => switchTab("suggested")}>Suggested fixes</button><button type="button" disabled={busy} aria-pressed={tab === "saved"} onClick={() => switchTab("saved")}>Saved choices{saved.length ? ` (${saved.length})` : ""}</button></nav>
        {loading ? <p role="status">Checking current columns and suggested fixes…</p> : tab === "suggested" ? <>
          <div className="quick-clean-groups">{groups.length ? groups.map(group => {
            const checked = selected.includes(group.id), action = group.steps[0]?.body.action, options = { ...group.steps[0]?.body.parameters, ...overrides[group.id] };
            const included = group.columns.filter(column => !(excluded[group.id] || []).includes(column));
            return <section key={group.id} className="quick-clean-group"><label className="quick-clean-group-choice"><input type="checkbox" disabled={busy} checked={checked} onChange={event => { setSelected(current => event.target.checked ? [...current, group.id] : current.filter(id => id !== group.id)); invalidate(); }} /><span><strong>{group.label}</strong><small>{group.count.toLocaleString()} issue flags · {included.length} selected columns</small></span><span className="quick-clean-safety">{group.safety === "safe" ? "Suggested" : "Review choice"}</span></label><p>{group.description}</p>
              {checked && action === "normalize_capitalization" && <label className="setting">Text should look like<select disabled={busy} value={String(options.strategy || "title")} onChange={event => parameter(group, "strategy", event.target.value)}><option value="title">Title</option><option value="upper">UPPER</option><option value="lower">lower</option></select></label>}
              {checked && action === "normalize_boolean" && <label className="setting">Boolean labels<select disabled={busy} value={String(options.format || "true_false")} onChange={event => parameter(group, "format", event.target.value)}><option value="true_false">true / false</option><option value="yes_no">Yes / No</option><option value="one_zero">1 / 0</option></select></label>}
              {checked && action === "normalize_dates" && <label className="setting">Date output format<select disabled={busy} value={String(options.output_format || "YYYY-MM-DD")} onChange={event => parameter(group, "output_format", event.target.value)}>{DATE_FORMAT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><small>Unconfirmed ambiguous dates are preserved. Input day/month order is not guessed.</small></label>}
              {checked && action === "normalize_time" && <label className="setting">Clock format<select disabled={busy} value={String(options.format || "24_hour")} onChange={event => parameter(group, "format", event.target.value)}><option value="24_hour">24-hour · 14:30:00</option><option value="12_hour">12-hour · 02:30:00 PM</option></select></label>}
              <details><summary>More options · choose columns</summary><div className="quick-clean-columns">{group.columns.map(column => <label key={column}><input type="checkbox" disabled={busy || !checked} checked={!(excluded[group.id] || []).includes(column)} onChange={event => { setExcluded(current => ({ ...current, [group.id]: event.target.checked ? (current[group.id] || []).filter(name => name !== column) : [...(current[group.id] || []), column] })); invalidate(); }} />{column}</label>)}</div></details>
            </section>;
          }) : <p>No common notation fixes are currently suggested. Use guided review for findings that need your decision.</p>}</div>
          {!!suggested?.deferred.length && <details className="quick-clean-deferred"><summary>Other findings need a separate decision ({suggested.deferred.length} types)</summary><ul>{suggested.deferred.map((item, index) => <li key={`${item.kind}-${index}`}><strong>{item.label} · {item.count.toLocaleString()} flags</strong><p>{item.reason}</p></li>)}</ul>{onGuided && <Button variant="outline" disabled={busy} onClick={onGuided}>Open guided review</Button>}</details>}
        </> : <section className="quick-clean-saved"><p>Reuse named choices on matching columns. Every file receives a fresh compatibility check and preview before you apply anything.</p>{saved.length ? <><label className="setting">Saved choices<select disabled={busy} value={activeSaved} onChange={event => { const choice = saved.find(item => item.id === event.target.value); if (choice) loadChoice(choice); else { setActiveSaved(""); setSavedSteps([]); setSavedWarnings([]); invalidate(); } }}><option value="">Choose saved choices</option>{saved.map(choice => <option key={choice.id} value={choice.id}>{choice.name}</option>)}</select></label>{currentSaved && <><p>{savedSteps.length} compatible actions in {new Set(savedSteps.map(step => step.body.column)).size} columns.</p><details><summary>See loaded actions</summary><ul>{savedSteps.map((step, index) => <li key={index}>{step.body.column} · {actionLabels[step.body.action] || step.body.action}</li>)}</ul></details><Button variant="ghost" disabled={busy} onClick={() => { try { setSaved(deleteReusableChoice(activeSaved)); setActiveSaved(""); setSavedSteps([]); setSavedWarnings([]); invalidate(); setNotice("Saved choices deleted from this browser."); } catch (reason) { setError((reason as Error).message); } }}>Delete these saved choices</Button></>}</> : <p>No saved choices yet. Select suggested fixes and give them a name below.</p>}{savedWarnings.length > 0 && <div className="notice" role="status"><strong>Compatibility review</strong><ul>{savedWarnings.map(warning => <li key={warning}>{warning}</li>)}</ul></div>}</section>}
        {steps.length > 0 && <div className="quick-clean-selection"><strong>{steps.length} column actions selected</strong><small>Each selected fix covers its eligible cells in the selected columns.</small><Button disabled={busy || loading || steps.length > 100} variant="outline" onClick={() => void run()}>Preview all selected fixes</Button></div>}
        {review && <section className="quick-clean-preview" aria-label="Combined cleaning preview"><h3>{review.changed_cells.toLocaleString()} cell changes proposed</h3>{!!review.removed_rows && <p><strong>{review.removed_rows.toLocaleString()} duplicate rows would be removed; the first occurrence is kept.</strong></p>}<p>{review.operations.length} actions reviewed against the current spreadsheet. Counts across steps may include the same cell more than once.</p>{review.operations.map((entry, index) => <details key={index} open={review.operations.length === 1}><summary>{entry.column} · {actionLabels[entry.action] || entry.action} · {entry.changed_cells.toLocaleString()} changes</summary>{!!entry.interpreted_dates && <p>{entry.interpreted_dates} dates will receive confirmed interpretation metadata.</p>}{entry.examples?.length ? <div className="quick-clean-example-scroll"><table><thead><tr><th>Spreadsheet row</th><th>Before</th><th>After</th></tr></thead><tbody>{entry.examples.map((example, exampleIndex) => <tr key={exampleIndex}><td>{example.spreadsheet_row ?? (example.row_index ?? 0) + 2}</td><td>{text(example.before)}</td><td>{text(example.after)}</td></tr>)}</tbody></table></div> : <p>No cell values change in this action.</p>}{entry.warnings?.map((warning, warningIndex) => <p className="notice" key={warningIndex}>{warning}</p>)}</details>)}{!canApply && <p className="notice">These choices would not change any cell values. Adjust your choices or return to the spreadsheet.</p>}</section>}
        {steps.length > 0 && <details className="quick-clean-save"><summary>Save these choices for similar files</summary><p>Stores action settings and column names in this browser. Input date-order judgments, row edits, accepted findings and cell values are excluded.</p><label className="setting">Name<input maxLength={80} disabled={busy} value={choiceName} placeholder="For example: Monthly sales format" onChange={event => setChoiceName(event.target.value)} /></label><Button disabled={busy || !choiceName.trim() || !sanitizeReusableDecisions(steps).length} variant="outline" onClick={save}>Save choices</Button></details>}
      </>}
      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <div className="error blocking-error" role="alert" ref={alert}><strong>{applied ? "Refresh needed" : "Cannot continue"}</strong><p>{error}</p></div>}
      {busy && <div className="simplify-progress" role="status"><strong>{job?.stage || "Preparing your review…"}</strong>{job?.total_units ? <progress aria-label="Quick cleaning progress" value={job.completed_units || 0} max={job.total_units} /> : <progress aria-label="Quick cleaning progress" />}<Button variant="outline" onClick={() => void cancel()}>Cancel job</Button></div>}
    </div>
    {!applied && <footer className="simplify-footer"><span>{review ? "Preview reviewed. Apply to your current working copy." : "Select fixes, then preview them together."}</span><Button disabled={busy || loading || !canApply || steps.length > 100} onClick={() => void run(true)}>Apply reviewed fixes</Button></footer>}
  </div></div>;
}

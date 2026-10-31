"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, ListChecks, X } from "lucide-react";
import type { Profile } from "@/lib/types";
import { Button } from "./ui/button";

const aliases: Record<string, string> = {
  missing_values: "missing", extra_whitespace: "whitespace", invalid_dates: "invalid_date",
  ambiguous_dates: "ambiguous_date", date_format_inconsistency: "date_format",
  case_inconsistency: "capitalization", currency_inconsistency: "currency",
  percentage_inconsistency: "percentage", symbol_inconsistency: "symbol",
  phone_inconsistency: "phone", invalid_phone: "phone", type_mismatch: "type",
  boolean_inconsistency: "boolean", invalid_email: "email", time_format: "time",
  duration_format: "duration", duplicate_rows: "duplicate",
};
const labels: Record<string, string> = {
  missing: "Missing values", missing_marker: "Possible missing-value labels",
  whitespace: "Extra whitespace", capitalization: "Capitalization", boolean: "Mixed boolean labels",
  invalid_date: "Invalid dates", ambiguous_date: "Ambiguous dates", date_format: "Mixed date formats",
  time: "Clock time format", invalid_time: "Invalid clock time", duration: "Duration format",
  invalid_duration: "Invalid duration", currency: "Currency notation", percentage: "Percentage notation",
  symbol: "Unit notation", phone: "Phone format", email: "Invalid email", type: "Type mismatch",
  odd_value: "Odd values", duplicate: "Duplicate rows", cross_column: "Related column rule",
  outlier: "Unusual measurements", data_format: "Data format interpretation",
  invalid_data_format: "Invalid data format", rule_negative: "Negative values not allowed",
  rule_required: "Required values", rule_unique: "Unique value rule", rule_allowed: "Allowed values rule",
  rule_pattern: "Text pattern rule", rule_type: "Declared type rule", rule_range: "Numeric range rule",
  rule_date_range: "Date range rule",
};

export function guidedIssueLabel(kind: string): string {
  const canonical = aliases[kind] || kind;
  return labels[canonical] || canonical.replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
}
export type GuidedIssueGroup = { key: string; column: string; kind: string; count: number };
const groupKey = (column: string, kind: string) => JSON.stringify([column, kind]);
const countValue = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;

/** One decision target per column and issue kind, using counts from the entire file. */
export function canonicalIssueGroups(profile: Profile): GuidedIssueGroup[] {
  const groups = new Map<string, GuidedIssueGroup>();
  for (const column of profile.columns) {
    for (const issue of column.issues) {
      const kind = aliases[issue.issue] || issue.issue;
      const count = countValue(issue.count);
      if (!count || kind === "duplicate") continue;
      const key = groupKey(column.column_name, kind);
      const existing = groups.get(key);
      groups.set(key, { key, column: column.column_name, kind, count: (existing?.count || 0) + count });
    }
    const markerCount = countValue(column.missing_marker_review?.count);
    const markerKey = groupKey(column.column_name, "missing_marker");
    if (markerCount && !groups.has(markerKey)) groups.set(markerKey, { key: markerKey, column: column.column_name, kind: "missing_marker", count: markerCount });
  }
  if (countValue(profile.duplicate_rows) && profile.columns.length) {
    const column = profile.columns[0].column_name;
    const key = groupKey(column, "duplicate");
    groups.set(key, { key, column, kind: "duplicate", count: countValue(profile.duplicate_rows) });
  }
  return [...groups.values()];
}

type Step = GuidedIssueGroup & { status: "pending" | "reviewed" | "skipped" | "resolved"; opened: boolean };
type Walkthrough = { fileId: string; revision: number; steps: Step[]; current: string | null; notice: string };
type Props = {
  fileId: string; revision: number; profile: Profile; open: boolean; busy: boolean;
  onFix: (item: { column: string; kind: string }) => Promise<void>;
  onClose: () => void; onFinish: () => void; onQuickReview: () => void;
  onTool?: (tool: string, column: string) => void;
};

function recommendation(kind: string): string {
  if (kind === "whitespace") return "Trim extra whitespace. Review the affected cells before applying.";
  if (kind === "missing_marker") return "Choose whether labels such as N/A mean empty cells or should stay as text.";
  if (kind === "missing" || kind === "rule_required") return "Choose a suitable fill method, a constant, or leave the values empty.";
  if (kind === "duplicate") return "Review exact duplicate rows, then choose whether to remove the repeated rows.";
  if (kind === "cross_column") return "Review the related-column rule and its expected values before correcting the flagged rows.";
  if (kind === "outlier") return "Review unusual measurements. You can keep valid values, clear them, or choose reviewed limits.";
  if (kind === "capitalization") return "Choose Title, UPPER or lower for the eligible text in this column.";
  if (kind === "boolean") return "Choose one consistent representation, such as Yes / No or True / False.";
  if (kind === "ambiguous_date" || kind === "date_format") return "Choose how dates should be interpreted and how they should be displayed.";
  if (kind.startsWith("invalid_") || ["email", "type", "odd_value"].includes(kind)) return "Inspect these values before deciding how to correct them. No values are cleared automatically.";
  return "Review the suggested correction and choose where to apply it. One decision can cover eligible cells in this column.";
}

function loadWalkthrough(fileId: string, revision: number, groups: GuidedIssueGroup[]): Walkthrough {
  const fresh = (): Walkthrough => ({ fileId, revision, steps: groups.map(group => ({ ...group, status: "pending", opened: false })), current: groups[0]?.key || null, notice: "" });
  try {
    const saved = JSON.parse(sessionStorage.getItem(`dataneat-guided-cleaning-${fileId}`) || "null");
    if (!saved || saved.version !== 1 || !Array.isArray(saved.steps) || saved.steps.length > 20000 || !Number.isInteger(saved.revision)) return fresh();
    const seen = new Set<string>();
    const steps: Step[] = [];
    for (const item of saved.steps) {
      if (!item || typeof item.column !== "string" || typeof item.kind !== "string" || item.column.length > 10000 || item.kind.length > 200 || !["pending", "reviewed", "skipped", "resolved"].includes(item.status)) continue;
      const key = groupKey(item.column, item.kind);
      if (seen.has(key)) continue;
      seen.add(key);
      steps.push({ key, column: item.column, kind: item.kind, count: countValue(item.count), status: item.status, opened: item.opened === true });
    }
    const state = { fileId, revision: saved.revision, steps, current: typeof saved.current === "string" ? saved.current : null, notice: "" };
    return reconcile(state, groups, revision);
  } catch { return fresh(); }
}

function reconcile(previous: Walkthrough, groups: GuidedIssueGroup[], revision: number, attempted?: { key: string; before: number }): Walkthrough {
  const active = new Map(groups.map(group => [group.key, group]));
  const seen = new Set<string>();
  const steps = previous.steps.map(item => {
    seen.add(item.key);
    const current = active.get(item.key);
    return { ...item, count: current?.count || 0, status: !current ? "resolved" as const : item.status === "resolved" ? "pending" as const : item.status };
  });
  for (const group of groups) if (!seen.has(group.key)) steps.push({ ...group, status: "pending", opened: false });
  const priorCurrent = steps.find(item => item.key === previous.current);
  const current = priorCurrent?.status === "pending" ? priorCurrent.key : steps.find(item => item.status === "pending")?.key || null;
  let notice = previous.notice;
  if (attempted && revision !== previous.revision) {
    const remaining = active.get(attempted.key)?.count || 0;
    notice = remaining ? `Updated. ${remaining.toLocaleString()} cells or rows are still flagged for this issue. You can review them or move to the next issue.` : "This issue is no longer flagged. The next issue is ready to review.";
  } else if (revision !== previous.revision) notice = "Counts updated from your current sheet.";
  return { ...previous, revision, steps, current, notice };
}

export function GuidedCleaning({ fileId, revision, profile, open, busy, onFix, onClose, onFinish, onQuickReview, onTool }: Props) {
  const groups = useMemo(() => canonicalIssueGroups(profile), [profile]);
  const [walkthrough, setWalkthrough] = useState<Walkthrough | null>(null);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");
  const attempted = useRef<{ key: string; revision: number; before: number } | null>(null);
  const previousFile = useRef(fileId);
  useEffect(() => {
    if (previousFile.current !== fileId) { previousFile.current = fileId; attempted.current = null; setError(""); }
    const attempt = attempted.current;
    if (attempt && attempt.revision !== revision) attempted.current = null;
    setWalkthrough(previous => previous?.fileId === fileId
      ? reconcile(previous, groups, revision, attempt && attempt.revision !== revision ? attempt : undefined)
      : loadWalkthrough(fileId, revision, groups));
  }, [fileId, revision, groups]);
  useEffect(() => {
    if (!walkthrough || walkthrough.fileId !== fileId) return;
    try { sessionStorage.setItem(`dataneat-guided-cleaning-${fileId}`, JSON.stringify({ version: 1, revision: walkthrough.revision, steps: walkthrough.steps, current: walkthrough.current })); } catch { /* The walkthrough remains usable when browser storage is unavailable. */ }
  }, [walkthrough, fileId]);

  if (!open) return null;
  if (!walkthrough || walkthrough.fileId !== fileId) return <section className="guided-cleaning" aria-label="Guided cleaning"><p role="status">Preparing your next issue…</p></section>;
  const current = walkthrough.steps.find(item => item.key === walkthrough.current && item.status === "pending");
  const reviewed = walkthrough.steps.filter(item => item.opened || item.status === "reviewed" || item.status === "resolved").length;
  const skipped = walkthrough.steps.filter(item => item.status === "skipped").length;
  const resolved = walkthrough.steps.filter(item => item.status === "resolved").length;
  const processed = walkthrough.steps.filter(item => item.status !== "pending").length;
  const total = walkthrough.steps.length;
  const disabled = busy || opening;
  const remainingGroups = groups.length;
  const currentIndex = current ? walkthrough.steps.findIndex(item => item.key === current.key) + 1 : total;

  function moveNext(status: "reviewed" | "skipped") {
    if (!current) return;
    attempted.current = null;
    setError("");
    setWalkthrough(previous => {
      if (!previous) return previous;
      const steps = previous.steps.map(item => item.key === current.key ? { ...item, status } : item);
      return { ...previous, steps, current: steps.find(item => item.status === "pending")?.key || null, notice: status === "skipped" ? "Skipped for this walkthrough. Its issue flags remain on the sheet." : "Moved to the next issue. Any remaining flags stay visible on the sheet." };
    });
  }
  async function fixCurrent() {
    if (!current || disabled) return;
    setOpening(true); setError("");
    attempted.current = { key: current.key, revision, before: current.count };
    setWalkthrough(previous => previous ? { ...previous, steps: previous.steps.map(item => item.key === current.key ? { ...item, opened: true } : item), notice: "Review the correction and confirm it when ready. Opening a correction does not change your data." } : previous);
    try {
      if (onTool && ["cross_column", "outlier"].includes(current.kind)) onTool(current.kind === "outlier" ? "outliers" : "cross_column", current.column);
      else await onFix({ column: current.column, kind: current.kind });
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Could not open this correction. Please retry."); }
    finally { setOpening(false); }
  }
  function revisit() {
    attempted.current = null;
    const reset = groups.map(group => ({ ...group, status: "pending" as const, opened: false }));
    setWalkthrough({ fileId, revision, steps: reset, current: reset[0]?.key || null, notice: "Remaining issues are ready for another review." });
    setError("");
  }
  return <section className="guided-cleaning" aria-labelledby="guided-cleaning-title">
    <header className="guided-heading"><div><small>One decision at a time · All rows included</small><h3 id="guided-cleaning-title"><ListChecks size={18} aria-hidden="true" />Guided cleaning</h3></div><Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={onClose} aria-label="Close guided cleaning"><X size={16} aria-hidden="true" />Close</Button></header>
    <div className="guided-progress"><progress value={processed} max={Math.max(1, total)} aria-label="Issue groups reviewed or skipped" /><span>{current ? `Issue ${currentIndex} of ${total}` : `${processed} of ${total} issue groups visited`}</span></div>
    {current ? <>
      <div className="guided-current"><div><strong>{current.kind === "duplicate" ? "Whole sheet" : current.column}</strong><h4>{guidedIssueLabel(current.kind)}</h4></div><span>{current.count.toLocaleString()} {current.kind === "duplicate" ? "rows" : "flags"}</span></div>
      <p>{recommendation(current.kind)}</p>
      {walkthrough.notice && <p className="guided-notice" role="status">{walkthrough.notice}</p>}
      <div className="guided-actions"><Button type="button" disabled={disabled} onClick={() => void fixCurrent()}>{opening ? "Opening…" : "Fix this type"}</Button><Button type="button" variant="outline" disabled={disabled} onClick={() => moveNext("skipped")}>Skip for now</Button>{current.opened && <Button type="button" variant="outline" disabled={disabled} onClick={() => moveNext("reviewed")}>Next issue<ArrowRight size={15} aria-hidden="true" /></Button>}</div>
      <small className="guided-scope-note">The correction opens with a scope to review. Eligible cells in this column can be handled together.</small>
    </> : <div className="guided-completion" aria-live="polite"><h4><CheckCircle2 size={18} aria-hidden="true" />Walkthrough complete</h4><p>{reviewed} issue groups reviewed · {skipped} skipped · {resolved} no longer flagged.</p><p>{remainingGroups ? `${remainingGroups} issue groups still have flags on your sheet. Review them before deciding whether the data is ready to export.` : "No issue groups are currently flagged. You can review your changes and export."}</p><div className="guided-actions"><Button type="button" disabled={disabled} onClick={onFinish}>Review &amp; export<ArrowRight size={15} aria-hidden="true" /></Button><Button type="button" variant="outline" disabled={disabled} onClick={onQuickReview}>Review suggested fixes</Button>{remainingGroups > 0 && <Button type="button" variant="outline" disabled={disabled} onClick={revisit}>Revisit remaining issues</Button>}</div></div>}
    {error && <div className="quality-error" role="alert"><strong>Cannot open this correction</strong><p>{error}</p></div>}
  </section>;
}

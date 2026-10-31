"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/types";
import { editorRequest } from "@/lib/workflow";
import { Button } from "./ui/button";
type Entry = { value: string; count: number; row_index: number };
export function UnifyTextValues({ fileId, column, onClose, onApplied }: { fileId: string; column: string; onClose: () => void; onApplied: (count: number) => Promise<void> }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [revision, setRevision] = useState<number | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [count, setCount] = useState<number | null>(null);
  const [groups, setGroups] = useState<{values:string[];suggested:string}[]>([]);
  const [suggestionsVisible, setSuggestionsVisible] = useState(false);
  const [jobId,setJobId]=useState("");
  useEffect(()=>{const listener=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail.fileId===fileId&&detail.status)setJobId(["queued","running"].includes(detail.status.status)?detail.status.id:"");};window.addEventListener("dataneat-workflow-job",listener);return()=>window.removeEventListener("dataneat-workflow-job",listener);},[fileId]);
  useEffect(() => {
    const controller = new AbortController();
    api<{ revision: number; values: Entry[] }>(`/files/${fileId}/editor/text-values?column=${encodeURIComponent(column)}`, { signal: controller.signal }).then(data => { setEntries(data.values); setRevision(data.revision); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [fileId, column]);
  useEffect(()=>{const controller=new AbortController();api<{groups:{values:string[];suggested:string}[]}>(`/files/${fileId}/workflow/suggestions?column=${encodeURIComponent(column)}`,{signal:controller.signal}).then(data=>setGroups(data.groups)).catch(()=>{});return()=>controller.abort();},[fileId,column]);
  const body = { revision, column, row_index: entries.find(entry => selected.includes(entry.value))?.row_index ?? 0, scope: "values", action: "replace", value: target, parameters: { source_values: selected, purpose: "Unify text values" } };
  useEffect(() => {
    setCount(null); setError("");
    if (revision === null || selected.length < 2 || !target.trim()) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api<{ proposal: { changed_cells: number } }>(`/files/${fileId}/editor/fix`, { method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, confirmed: false }) }).then(data => setCount(data.proposal.changed_cells)).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    }, 350);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [fileId, revision, selected, target, entries, column]);
  async function apply() {
    setBusy(true); setError("");
    try {
      const data = await editorRequest<{ proposal: { changed_cells: number } }>(`/files/${fileId}/editor/fix`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, confirmed: true }) });
      await onApplied(data.proposal.changed_cells);
      onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const filtered = entries.filter(entry => entry.value.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <div className="unify-overlay"><section className="panel unify-dialog" role="dialog" aria-modal="true" aria-label={`Unify text values in ${column}`}>
    <div className="panel-heading"><h3>{column} · Unify text values</h3><Button variant="ghost" disabled={busy} onClick={onClose}>Close</Button></div>
    <p>Select at least two spellings and choose their final text. Exact matches are replaced in this column across every page; empty cells stay empty.</p>
    <button className="button outline" type="button" disabled={busy} aria-expanded={suggestionsVisible} onClick={()=>setSuggestionsVisible(!suggestionsVisible)}>Suggested spelling groups ({groups.length})</button>
    {suggestionsVisible&&<div><small>Local spelling similarity only, among up to 1,000 frequent values. Review the selection; no values are merged automatically.</small>{groups.map((group,i)=><button className="suggestion-group" key={i} disabled={busy} onClick={()=>{setSelected(group.values);setTarget(group.suggested);}}>{group.values.join(" / ")} — Review group</button>)}{!groups.length&&<p>No suggested groups. You can still select values manually.</p>}</div>}
    <label className="setting">Search values<input value={search} disabled={busy} onChange={e => setSearch(e.target.value)} placeholder="Search this column…" /></label>
    <small>{selected.length} selected · {entries.length} different text values</small>
    <div className="unify-values">{filtered.slice(0, 300).map(entry => <label key={entry.value}><input type="checkbox" disabled={busy} checked={selected.includes(entry.value)} onChange={e => setSelected(values => e.target.checked ? [...values, entry.value] : values.filter(value => value !== entry.value))} /><span>{entry.value}</span><small>{entry.count} cells</small></label>)}{filtered.length > 300 && <small>Showing 300 matches. Narrow your search to find more values.</small>}{revision !== null && filtered.length === 0 && <p>No matching text values.</p>}</div>
    {selected.length > 0 && <div className="unify-selected">{selected.map(value => <button type="button" disabled={busy} key={value} title="Remove from selection" onClick={() => setSelected(values => values.filter(item => item !== value))}>{value} ×</button>)}</div>}
    <label className="setting">Final text<input list="unify-target-values" value={target} disabled={busy} onChange={e => setTarget(e.target.value)} placeholder="For example: Cairo" /><datalist id="unify-target-values">{selected.map(value => <option key={value} value={value} />)}</datalist></label>
    <div role="status">{busy ? "Applying text unification…" : selected.length < 2 ? "Select at least two text values." : !target.trim() ? "Enter the final text." : count === null && !error ? "Calculating affected cells…" : count !== null ? `${count} cells will change in ${column}.` : ""}</div>
    {error && <p role="alert" className="error">{error}</p>}
    <Button disabled={busy || count === null || count === 0 || !!error} onClick={apply}>Apply change</Button>
    {busy&&jobId&&<Button variant="outline" onClick={()=>api(`/workflow-jobs/${jobId}/cancel`,{method:"POST"}).catch(e=>setError(e.message))}>Cancel job</Button>}
  </section></div>;
}

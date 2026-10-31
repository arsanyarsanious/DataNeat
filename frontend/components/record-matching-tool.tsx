"use client";

import { useState } from "react";
import { Button } from "./ui/button";
import { ActionReview, Notes, type ToolProps } from "./quality-tool-ui";

type Pair = {
  left_row: number;
  right_row: number;
  score: number;
  fields: { column: string; left: unknown; right: unknown; similarity: number | null; comparison: string }[];
  left_values: Record<string, unknown>;
  right_values: Record<string, unknown>;
  conflicts: string[];
};
type MatchingReview = {
  pairs: Pair[];
  row_count: number;
  compared_pairs: number;
  matched_pairs: number;
  returned_pairs: number;
  kept_pairs_skipped: number;
  truncated: boolean;
  coverage?: { searched_rows?: number; rows_without_block_value?: number; sampled_candidates?: boolean };
  warnings?: string[];
};

function display(value: unknown) {
  if (value === null || value === undefined || value === "") return "empty";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function RecordMatchingTool({ columns, run, busy, initialColumn }: ToolProps) {
  const names = columns.map(column => column.column_name);
  const descriptive = columns.filter(column=>column.detected_type!=="identifier"&&column.intent?.type!=="identifier"&&["text","category","categorical","email"].includes(column.detected_type)).map(column=>column.column_name);
  const defaultColumns = [...new Set([initialColumn, ...descriptive, ...names])].filter((name): name is string => Boolean(name)).slice(0, 2);
  const [selected, setSelected] = useState<string[]>(defaultColumns);
  const [threshold, setThreshold] = useState("85");
  const [blockBy, setBlockBy] = useState("");
  const [result, setResult] = useState<MatchingReview | null>(null);
  const [pairKey, setPairKey] = useState("");
  const [choices, setChoices] = useState<Record<string, "left" | "right">>({});
  const [keepRow, setKeepRow] = useState<number | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const thresholdNumber = Number(threshold);
  const validThreshold = threshold.trim() !== "" && Number.isFinite(thresholdNumber) && thresholdNumber >= 0 && thresholdNumber <= 100;
  const valid = selected.length >= 2 && selected.length <= 5 && validThreshold;
  const settings = { tool: "record_matching", action: "review", columns: selected, threshold: thresholdNumber / 100, block_by: blockBy };
  const pair = result?.pairs.find(item => `${item.left_row}:${item.right_row}` === pairKey);
  const fieldNames = pair ? Object.keys(pair.left_values) : [];
  const unresolved = pair?.conflicts.filter(column => !choices[column]) || [];

  function invalidate() {
    setResult(null);
    setPairKey("");
    setChoices({});
    setKeepRow(null);
    setConfirmed(false);
    setError("");
  }

  function choosePair(item: Pair) {
    setPairKey(`${item.left_row}:${item.right_row}`);
    setChoices({});
    setKeepRow(item.left_row);
    setConfirmed(false);
    setError("");
  }

  async function analyze() {
    setError("");
    try {
      const response = await run("analyze", settings);
      if (!response) return;
      const review = (response?.review ?? response) as MatchingReview | undefined;
      if (!review || !Array.isArray(review.pairs)) throw new Error("The record review could not be read. Please retry.");
      setResult(review);
      setPairKey("");
      setChoices({});
      setKeepRow(null);
      setConfirmed(false);
      if (review.pairs.length) choosePair(review.pairs[0]);
    } catch (cause) {
      setResult(null);
      setError((cause as Error).message);
    }
  }

  const pairSettings = pair ? { ...settings, left_row: pair.left_row, right_row: pair.right_row } : null;

  return <div className="quality-card">
    <h3>Find similar records</h3>
    <p className="quality-muted">Compare two to five fields to find possible duplicate records. Review each pair before merging.</p>
    <fieldset disabled={busy}>
      <legend>Matching columns · {selected.length} selected</legend>
      <div className="quality-checkboxes">
        {names.map(name => <label key={name} className="quality-check">
          <input type="checkbox" checked={selected.includes(name)} disabled={!selected.includes(name) && selected.length >= 5} onChange={event => {
            setSelected(current => event.target.checked ? [...current, name] : current.filter(column => column !== name));
            invalidate();
          }} />
          <span>{name}</span>
        </label>)}
      </div>
    </fieldset>
    <div className="quality-fields">
      <label className="setting">Minimum similarity (%)
        <input aria-label="Minimum record similarity percentage" type="number" min="0" max="100" step="1" value={threshold} disabled={busy} onChange={event => { setThreshold(event.target.value); invalidate(); }} />
      </label>
      <label className="setting">Only compare records with the same value in
        <select aria-label="Exact blocking column" value={blockBy} disabled={busy} onChange={event => { setBlockBy(event.target.value); invalidate(); }}>
          <option value="">No exact blocking column</option>
          {names.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>
    </div>
    <p className="quality-muted">Identifiers, email addresses and numeric fields require exact agreement. Empty fields never count as a match. Similarity is a comparison score, not a probability of identity.</p>
    {!valid && <p className="quality-muted">Select two to five columns and enter a similarity from 0 to 100.</p>}
    <div className="quality-actions"><Button type="button" disabled={busy || !valid} onClick={() => void analyze()}>Find possible duplicates</Button></div>
    {error && <div className="quality-error" role="alert">{error}</div>}
    {result && <>
      <p><strong>{result.returned_pairs} of {result.matched_pairs} possible pairs shown</strong> · {result.compared_pairs.toLocaleString()} pairs compared across {result.row_count.toLocaleString()} rows.</p>
      <p className="quality-muted">This bounded neighborhood search does not check every possible pair.{result.truncated ? " The search or display limit was reached; more matches may exist." : ""}</p>
      {result.kept_pairs_skipped > 0 && <p className="quality-muted">{result.kept_pairs_skipped} reviewed pairs remain marked as separate records.</p>}
      <Notes warnings={result.warnings} />
      {!result.pairs.length && <p>No matching pairs were found in the searched candidates. The bounded search does not check every possible pair.</p>}
      {result.pairs.length > 0 && <>
        <div className="quality-pair-list" aria-label="Possible duplicate pairs">
          {result.pairs.map(item => <Button type="button" variant="outline" key={`${item.left_row}:${item.right_row}`} className={pairKey === `${item.left_row}:${item.right_row}` ? "quality-pair-active" : ""} disabled={busy} aria-pressed={pairKey === `${item.left_row}:${item.right_row}`} onClick={() => choosePair(item)}>
            Rows {item.left_row + 2} &amp; {item.right_row + 2} · {(item.score * 100).toFixed(1)}% similarity
          </Button>)}
        </div>
        {pair && pairSettings && <section className="quality-card" aria-label={`Review records in rows ${pair.left_row + 2} and ${pair.right_row + 2}`}>
          <h4>Review rows {pair.left_row + 2} and {pair.right_row + 2}</h4>
          <p className="quality-muted">Choose the value to retain for every conflicting field. A value present in only one record is preserved automatically.</p>
          <div className="quality-table-scroll">
            <table>
              <thead><tr><th scope="col">Field</th><th scope="col">Row {pair.left_row + 2}</th><th scope="col">Row {pair.right_row + 2}</th><th scope="col">Value to retain</th></tr></thead>
              <tbody>{fieldNames.map(column => {
                const conflict = pair.conflicts.includes(column);
                return <tr key={column}>
                  <th scope="row">{column}</th>
                  <td>{display(pair.left_values[column])}</td>
                  <td>{display(pair.right_values[column])}</td>
                  <td>{conflict ? <select aria-label={`Retain value for ${column}`} disabled={busy} value={choices[column] || ""} onChange={event => {
                    const value = event.target.value as "left" | "right" | "";
                    setChoices(current => { const next = { ...current }; if (value) next[column] = value; else delete next[column]; return next; });
                    setConfirmed(false);
                  }}>
                    <option value="">Choose a value</option>
                    <option value="left">Row {pair.left_row + 2}</option>
                    <option value="right">Row {pair.right_row + 2}</option>
                  </select> : <span className="quality-muted">Preserve available value</span>}</td>
                </tr>;
              })}</tbody>
            </table>
          </div>
          <div className="quality-fields">
            <label className="setting">Keep original row number
              <select aria-label="Original row to retain after merge" value={keepRow ?? pair.left_row} disabled={busy} onChange={event => { setKeepRow(Number(event.target.value)); setConfirmed(false); }}>
                <option value={pair.left_row}>Row {pair.left_row + 2}</option>
                <option value={pair.right_row}>Row {pair.right_row + 2}</option>
              </select>
            </label>
          </div>
          {unresolved.length > 0 && <p className="quality-muted">Choose values for {unresolved.length} conflicting {unresolved.length === 1 ? "field" : "fields"} before previewing a merge.</p>}
          <label className="quality-check"><input type="checkbox" checked={confirmed} disabled={busy || unresolved.length > 0} onChange={event => setConfirmed(event.target.checked)} /><span>I reviewed the field choices. Merge these two records into one.</span></label>
          <ActionReview key={`merge-${pairKey}`} settings={{ ...pairSettings, action: "merge", keep_row: keepRow ?? pair.left_row, choices, confirmed: true }} run={run} busy={busy} disabled={!confirmed || unresolved.length > 0} label="Merge reviewed pair" />
          <div className="quality-card">
            <h4>These are separate records</h4>
            <p className="quality-muted">Keep both to dismiss this pair. It will be reviewed again if either record changes.</p>
            <ActionReview key={`keep-${pairKey}`} settings={{ ...pairSettings, action: "keep_both" }} run={run} busy={busy} label="Keep both records" allowNoChanges />
          </div>
        </section>}
      </>}
    </>}
  </div>;
}

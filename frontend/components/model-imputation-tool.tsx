"use client";

import { useEffect, useState } from "react";
import type { Column } from "@/lib/types";
import { Notes, type ToolProps } from "./quality-tool-ui";
import { Button } from "./ui/button";
import { getImputationReadiness } from "@/lib/imputation-readiness";
import { ImputationReadinessNotice } from "./imputation-controls";

type ModelSettings = {
  method: "knn" | "iterative";
  target: string;
  helpers: string[];
  neighbors: number;
  max_iter: number;
};
type ModelReview = {
  target: string;
  method: string;
  missing_count: number;
  filled_count: number;
  skipped_count: number;
  donor_count: number;
  fit_donor_count: number;
  excluded_estimates: number;
  warnings: string[];
  examples: { row_index: number; spreadsheet_row: number; before: unknown; after: number }[];
  validation: {
    status: "available" | "unavailable";
    held_out_count: number;
    mae: number | null;
    baseline_mae: number | null;
    better_than_baseline?: boolean;
    reason?: string;
    explanation?: string;
  };
};

function ordinaryNumeric(column: Column) {
  return ["integer", "decimal"].includes(column.detected_type)
    && (!column.intent?.type || column.intent.type === "numeric");
}
function shownNumber(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString(undefined, { maximumSignificantDigits: 5 }) : "Unavailable";
}

export function ModelImputationTool({ columns, run, busy, saved, initialColumn }: ToolProps) {
  const numeric = columns.filter(ordinaryNumeric);
  const targets = numeric.filter(column => column.missing_count > 0);
  const helperColumns = numeric.filter(column => !column.missing_marker_review?.count);
  const prior = saved?.model_imputation ?? saved;
  const [target, setTarget] = useState(() => targets.some(column => column.column_name === initialColumn)
    ? initialColumn! : targets.some(column => column.column_name === prior?.target) ? prior.target : targets[0]?.column_name ?? "");
  const [method, setMethod] = useState<"knn" | "iterative">(prior?.method === "iterative" ? "iterative" : "knn");
  const [helpers, setHelpers] = useState<string[]>(() => Array.isArray(prior?.helpers)
    ? prior.helpers.filter((name: unknown) => typeof name === "string" && name !== target && helperColumns.some(column => column.column_name === name)).slice(0, 8) : []);
  const [neighbors, setNeighbors] = useState<number>(Number.isInteger(prior?.neighbors) && prior.neighbors >= 1 && prior.neighbors <= 30 ? prior.neighbors : 5);
  const [maxIter, setMaxIter] = useState<number>(Number.isInteger(prior?.max_iter) && prior.max_iter >= 1 && prior.max_iter <= 20 ? prior.max_iter : 10);
  const [analysis, setAnalysis] = useState<{ key: string; data: ModelReview } | null>(null);
  const [acknowledge, setAcknowledge] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const settings: ModelSettings = { method, target, helpers, neighbors, max_iter: maxIter };
  const key = JSON.stringify(settings);
  const waiting = busy || pending;
  const targetColumn = targets.find(column => column.column_name === target);
  const readiness = getImputationReadiness(targetColumn);
  const imputationBlocked = !readiness.ready;
  const valid = !!targetColumn && !imputationBlocked
    && helpers.length > 0 && helpers.length <= 8
    && helpers.every(name => name !== target && helperColumns.some(column => column.column_name === name))
    && Number.isInteger(neighbors) && neighbors >= 1 && neighbors <= 30
    && Number.isInteger(maxIter) && maxIter >= 1 && maxIter <= 20;
  const result = analysis?.key === key ? analysis.data : null;
  const applicable = !!result && result.filled_count > 0 && acknowledge && valid;

  useEffect(() => { setAnalysis(null); setAcknowledge(false); setError(""); setMessage(""); }, [key, columns]);

  function toggleHelper(name: string) {
    setHelpers(current => current.includes(name) ? current.filter(value => value !== name) : current.length < 8 ? [...current, name] : current);
  }
  async function analyze() {
    if (!valid || waiting) return;
    setPending(true); setError(""); setMessage(""); setAnalysis(null); setAcknowledge(false);
    try {
      const response = await run("analyze", { tool: "model_imputation", ...settings, acknowledge: false });
      if (!response) return;
      const data = response?.review ?? response?.result ?? response;
      if (!data || typeof data.filled_count !== "number" || !data.validation) throw new Error("The model review could not be loaded. Analyze the current settings again.");
      setAnalysis({ key, data });
    } catch (caught) { setError((caught as Error).message); }
    finally { setPending(false); }
  }
  async function apply() {
    if (!applicable || waiting) return;
    setPending(true); setError(""); setMessage("");
    try {
      const response = await run("apply", { tool: "model_imputation", ...settings, acknowledge: true });
      if (!response) return;
      setAnalysis(null); setAcknowledge(false);
      setMessage("Estimates applied. Their dotted underline and cleaning history identify them as imputed values.");
    } catch (caught) { setError((caught as Error).message); }
    finally { setPending(false); }
  }

  return <section aria-label="Model imputation">
    <p className="quality-muted">Estimate missing measurements from related numeric columns. Review a test against hidden observed values before applying.</p>
    {!targets.length ? <div className="quality-card"><strong>No eligible target columns</strong><p>Choose a plain numeric column with empty cells. Resolve missing-value labels first. Identifiers, dates, currency, percentages and text use their existing cleaning tools.</p></div> : <>
      <div className="quality-fields">
        <label>Measurement to fill<select aria-label="Measurement to fill" value={target} disabled={waiting} onChange={event => { setTarget(event.target.value); setHelpers(current => current.filter(name => name !== event.target.value)); }}>
          {targets.map(column => <option key={column.column_name} value={column.column_name}>{column.column_name} · {column.missing_count.toLocaleString()} empty{getImputationReadiness(column).ready ? "" : " · Resolve other issues first"}</option>)}
        </select></label>
        <label>Estimation method<select aria-label="Estimation method" value={method} disabled={waiting || imputationBlocked} onChange={event => setMethod(event.target.value as ModelSettings["method"])}>
          <option value="knn">KNN — similar rows</option><option value="iterative">Iterative — relationships between columns</option>
        </select></label>
      </div>
      <ImputationReadinessNotice column={targetColumn} />
      <fieldset disabled={waiting || imputationBlocked} className="quality-card">
        <legend>Related helper measurements</legend>
        <p className="quality-muted">Choose 1–8 columns that help explain {target || "the target"}. Avoid helpers calculated from the target or information unavailable at the time of the observation.</p>
        <div className="quality-fields">
          {helperColumns.filter(column => column.column_name !== target).map(column => <label key={column.column_name} className="check"><input type="checkbox" checked={helpers.includes(column.column_name)} disabled={!helpers.includes(column.column_name) && helpers.length >= 8} onChange={() => toggleHelper(column.column_name)} />{column.column_name}</label>)}
        </div>
        {!helperColumns.some(column => column.column_name !== target) && <p>No other eligible numeric measurements are available.</p>}
      </fieldset>
      <details className="quality-card"><summary>More options</summary><div className="quality-fields">
        {method === "knn" ? <label>Number of similar rows<input aria-label="Number of similar rows" type="number" min={1} max={30} step={1} value={neighbors} disabled={waiting || imputationBlocked} onChange={event => setNeighbors(event.target.valueAsNumber)} /></label>
          : <label>Maximum fitting rounds<input aria-label="Maximum fitting rounds" type="number" min={1} max={20} step={1} value={maxIter} disabled={waiting || imputationBlocked} onChange={event => setMaxIter(event.target.valueAsNumber)} /></label>}
      </div><p className="quality-muted">Fitting uses up to 2,000 original donor rows. A run supports up to 10,000 empty target cells and 8 helpers. Previous estimates are excluded from evidence.</p></details>
      <div className="quality-actions"><Button type="button" variant="outline" onClick={() => void analyze()} disabled={waiting || !valid}>{waiting ? "Working…" : "Analyze estimates"}</Button></div>
      {!helpers.length && <p className="quality-muted">Select at least one helper to analyze estimates.</p>}
      {result && <div className="quality-card" aria-live="polite">
        <h4>Review the proposed estimates</h4>
        <div className="quality-metrics"><span><strong>{result.filled_count.toLocaleString()}</strong> cells can be filled</span><span><strong>{result.skipped_count.toLocaleString()}</strong> remain empty</span><span><strong>{result.fit_donor_count.toLocaleString()}</strong> original training rows</span></div>
        {result.validation.status === "available" ? <div className="quality-card">
          <strong>Test on {result.validation.held_out_count.toLocaleString()} hidden observed values</strong>
          <div className="quality-metrics"><span>Model average error <strong>{shownNumber(result.validation.mae)}</strong></span><span>Median baseline error <strong>{shownNumber(result.validation.baseline_mae)}</strong></span></div>
          <p className="quality-muted">Lower error is better, in the measurement&apos;s original units. {result.validation.better_than_baseline ? "The model performed better than median filling in this test." : "The model did not improve on median filling in this test. Consider the simpler median option or choose different helpers."}</p>
        </div> : <p className="quality-muted"><strong>Validation unavailable.</strong> {result.validation.reason}</p>}
        <p className="quality-muted">This test uses observed rows; it cannot prove the unknown missing values are correct. Random holdout does not validate future or time-series prediction.</p>
        {result.examples.length > 0 && <div className="quality-table-scroll"><table><caption>Example estimates</caption><thead><tr><th>Spreadsheet row</th><th>Before</th><th>Estimated value</th></tr></thead><tbody>{result.examples.map(example => <tr key={example.row_index}><td>{example.spreadsheet_row}</td><td><em>empty</em></td><td>{shownNumber(example.after)}</td></tr>)}</tbody></table></div>}
        <Notes warnings={result.warnings} />
        {result.filled_count > 0 && <label className="check"><input type="checkbox" checked={acknowledge} disabled={waiting} onChange={event => setAcknowledge(event.target.checked)} />I understand these are estimates and have reviewed the helpers and validation.</label>}
        <div className="quality-actions"><Button type="button" disabled={waiting || !applicable} onClick={() => void apply()}>Apply estimates</Button></div>
      </div>}
    </>}
    {error && <div className="validation-error" role="alert"><strong>Cannot apply this change.</strong> {error}</div>}
    {message && <p role="status">{message}</p>}
  </section>;
}

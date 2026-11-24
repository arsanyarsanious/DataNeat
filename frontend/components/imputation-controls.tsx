import { DateMedianNotice } from "./date-median-notice";
import type { Column, Operation } from "@/lib/types";
import { imputationMethod, imputationMethods } from "@/lib/imputation-methods";
import { getImputationReadiness } from "@/lib/imputation-readiness";

export function ImputationReadinessNotice({ column }: { column?: Column }) {
  const readiness = getImputationReadiness(column);
  if (readiness.ready) return null;
  return <div className="blocking-action-error" role="alert"><div>
    <strong>Existing issues may affect your estimates</strong>
    <p>Review the issues below before estimating missing values.</p>
    {readiness.blocking_issues.length > 0 && <ul>{readiness.blocking_issues.map(issue => <li key={issue.kind}>
      {issue.label}: {issue.count.toLocaleString()}{issue.example_rows.length ? ` · Spreadsheet rows ${issue.example_rows.slice(0, 3).join(", ")}` : ""}
    </li>)}</ul>}
    <p>You may continue with the current data after accepting this risk, or return to cleaning.</p>
  </div></div>;
}

const names: Record<string, string> = {
  date_sequence: "Date pattern — complete a regular sequence",
  preserve: "Leave missing values unchanged",
  mean: "Mean",
  median: "Median",
  mode: "Mode",
  constant: "User-defined constant",
  forward_fill: "Forward fill",
  backward_fill: "Backward fill",
  linear_interpolation: "Linear interpolation",
  group_forward_fill: "Group forward fill",
  group_backward_fill: "Group backward fill",
};
export function ImputationControls({
  operation,
  columns,
  disabled,
  onChange,
}: {
  operation: Operation;
  columns: Column[];
  disabled: boolean;
  onChange: (parameters: Record<string, unknown>) => void;
}) {
  const column = columns.find((c) => c.column_name === operation.column);
  const info = column?.imputation;
  const readiness = getImputationReadiness(column);
  const controlsDisabled = disabled;
  const method = imputationMethod(String(operation.parameters.method || "preserve"));
  const groups = (operation.parameters.group_by || []) as string[];
  const ordered = [
    "date_sequence",
    "forward_fill",
    "backward_fill",
    "linear_interpolation",
    "group_forward_fill",
    "group_backward_fill",
  ].includes(method);
  function update(values: Record<string, unknown>) {
    onChange({ ...operation.parameters, method, ...values, confirmed: false });
  }
  return (
    <div className="imputation-controls">
      <h4>Imputation</h4>
      <p>
        {column?.column_name} · {column?.detected_type} ·{" "}
        {column?.missing_count} missing cells ({column?.missing_percentage}%).
        Up to {column?.missing_count} values could be filled; preview calculates
        the actual count.
      </p>
      <ImputationReadinessNotice column={column} />
      {!readiness.ready&&<label className="check"><input type="checkbox" disabled={disabled} checked={operation.parameters.inconsistencies_acknowledged===true} onChange={e=>update({inconsistencies_acknowledged:e.target.checked})}/>I accept that existing issues may affect estimates and want to continue with this data.</label>}
      {info && (
        <div className="imputation-recommendation">
          <strong>Suggested: {names[imputationMethod(info.method)]}</strong>
          <p>{info.explanation}</p>
          {info.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
          {info.contextual_recommendations?.map((item, i) => (
            <p key={i}>{item.explanation}</p>
          ))}
          <details>
            <summary>Distribution and missing patterns</summary>
            {info.statistics.numeric && (
              <p>
                Mean: {info.statistics.numeric.mean} · Median:{" "}
                {info.statistics.numeric.median} · Skewness:{" "}
                {info.statistics.numeric.skewness ?? "Insufficient evidence"} ·
                IQR outliers: {info.statistics.numeric.outlier_count}
              </p>
            )}
            <p>
              Observed categories:{" "}
              {info.statistics.frequencies
                .map((f) => `${f.value} (${f.count})`)
                .join(" · ") || "None"}
            </p>
            <p>
              Missing runs: {info.missing_pattern.missing_runs} · Longest run:{" "}
              {info.missing_pattern.longest_run} · Leading:{" "}
              {info.missing_pattern.leading_missing} · Trailing:{" "}
              {info.missing_pattern.trailing_missing}
            </p>
            {info.conditional_suggestions.map((text) => (
              <p key={text}>{text}</p>
            ))}
          </details>
        </div>
      )}
      <label className="setting">
        Imputation method
        <select
          aria-label={`Imputation method for ${operation.column}`}
          disabled={disabled}
          value={method}
          onChange={(e) => update({ method: e.target.value, date_estimate_acknowledged:false })}
        >
          {imputationMethods(info?.available_methods || ["preserve", "constant", "mode"]).map(
            (m) => (
              <option key={m} value={m} >
                {names[m]}
              </option>
            ),
          )}
        </select>
      </label>
      {["date","datetime"].includes(column?.detected_type||"")&&["median","group_median"].includes(method)&&<DateMedianNotice rounding={String(operation.parameters.date_rounding||"floor")} acknowledged={operation.parameters.date_estimate_acknowledged===true} disabled={controlsDisabled} onRounding={value=>update({date_rounding:value})} onAcknowledge={value=>update({date_estimate_acknowledged:value})}/>}
      {method==="date_sequence"&&<label className="setting">Interpret input dates<select value={String(operation.parameters.date_interpretation||"preserve")} disabled={controlsDisabled} onChange={e=>update({date_interpretation:e.target.value})}><option value="preserve">Keep known formats; block ambiguous dates</option><option value="day_first">Day / month / year</option><option value="month_first">Month / day / year</option></select><small>Detects fixed intervals and calendar month/year patterns from at least three original observations. Only interior gaps are filled when all observations match the same pattern.</small></label>}
      {method==="date_sequence"&&<label className="setting">Minimum original-date coverage<select aria-label="Minimum date pattern coverage" value={Number(operation.parameters.pattern_min_coverage??60)} disabled={controlsDisabled} onChange={e=>update({pattern_min_coverage:Number(e.target.value)})}>{[50,60,75,90,100].map(value=><option key={value} value={value}>{value}% of rows in each sequence</option>)}</select><small>At least 3 originals and the chosen share of rows are required. All original dates must match; previous estimates are excluded.</small></label>}
      {method === "constant" && (
        <label className="setting">
          Constant value
          <input
            aria-label={`Imputation constant for ${operation.column}`}
            disabled={controlsDisabled}
            value={String(operation.parameters.value ?? "")}
            onChange={(e) => update({ value: e.target.value })}
            placeholder="A meaningful value, not a missing marker"
          />
        </label>
      )}
      {method !== "preserve" && (
        <>
          <fieldset className="imputation-groups" disabled={controlsDisabled}>
            <legend>Group by ({method.startsWith("group_") ? "required" : "optional"}, up to five columns)</legend>
            <p>{method.startsWith("group_") ? "Select columns to keep unrelated sequences separate." : "Leave all unchecked to use the whole column. Select columns to calculate separately within each group."}</p>
            {columns
              .filter((c) => c.column_name !== operation.column)
              .map((c) => (
                <label key={c.column_name}>
                  <input
                    type="checkbox"
                    aria-label={`Group ${operation.column} by ${c.column_name}`}
                    checked={groups.includes(c.column_name)}
                    disabled={
                      controlsDisabled ||
                      (!groups.includes(c.column_name) && groups.length >= 5)
                    }
                    onChange={(e) =>
                      update({
                        group_by: e.target.checked
                          ? [...groups, c.column_name]
                          : groups.filter((v) => v !== c.column_name),
                        single_entity: false,
                      })
                    }
                  />{" "}
                  {c.column_name}
                </label>
              ))}
          </fieldset>
          {method.startsWith("group_") && !groups.length && (
            <p className="warning-text">
              Select grouping columns before previewing this method.
            </p>
          )}
          {ordered && (
            <>
              <label className="setting">
                Order by (ascending)
                <select
                  aria-label={`Imputation order for ${operation.column}`}
                  disabled={controlsDisabled}
                  value={String(operation.parameters.order_by || "")}
                  onChange={(e) => update({ order_by: e.target.value })}
                >
                  <option value="">Choose ordering column</option>{method==="date_sequence"&&<option value="__sheet_order__">Current sheet row order</option>}
                  {columns
                    .filter((c) => c.column_name !== operation.column)
                    .map((c) => (
                      <option key={c.column_name}>{c.column_name}</option>
                    ))}
                </select>
              </label>
              {!groups.length && (
                <label className="assumption-check">
                  <input
                    type="checkbox"
                    aria-label={`Single related sequence for ${operation.column}`}
                    disabled={controlsDisabled}
                    checked={operation.parameters.single_entity === true}
                    onChange={(e) =>
                      update({ single_entity: e.target.checked })
                    }
                  />
                  I confirm these rows belong to one related sequence, not
                  unrelated entities.
                </label>
              )}
              <p>
                Ordering must contain unique, non-missing numeric coordinates or
                valid ISO dates within each group. Rows are sorted only for
                calculation; spreadsheet order is preserved. Leading and
                trailing gaps are not extrapolated. Backward fill can leak
                future information.
              </p>
            </>
          )}
          <p>
            Only missing cells are filled. Missing group keys and groups without
            observations remain missing. These are estimates or placeholders,
            not verified facts. Statistical methods can reduce variance and
            distort distributions and correlations.
          </p>
        </>
      )}
    </div>
  );
}

import type { Column, Operation } from "@/lib/types";

const names: Record<string, string> = {
  preserve: "Leave missing values unchanged",
  mean: "Mean",
  median: "Median",
  mode: "Mode",
  constant: "User-defined constant",
  forward_fill: "Forward fill",
  backward_fill: "Backward fill",
  linear_interpolation: "Linear interpolation",
  group_mean: "Group mean",
  group_median: "Group median",
  group_mode: "Group mode",
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
  const method = String(operation.parameters.method || "preserve");
  const groups = (operation.parameters.group_by || []) as string[];
  const ordered = [
    "forward_fill",
    "backward_fill",
    "linear_interpolation",
    "group_forward_fill",
    "group_backward_fill",
  ].includes(method);
  function update(values: Record<string, unknown>) {
    onChange({ ...operation.parameters, ...values, confirmed: false });
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
      {info && (
        <div className="imputation-recommendation">
          <strong>Suggested: {names[info.method]}</strong>
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
          onChange={(e) => update({ method: e.target.value })}
        >
          {(info?.available_methods || ["preserve", "constant", "mode"]).map(
            (m) => (
              <option key={m} value={m}>
                {names[m]}
              </option>
            ),
          )}
        </select>
      </label>
      {method === "constant" && (
        <label className="setting">
          Constant value
          <input
            aria-label={`Imputation constant for ${operation.column}`}
            disabled={disabled}
            value={String(operation.parameters.value ?? "")}
            onChange={(e) => update({ value: e.target.value })}
            placeholder="A meaningful value, not a missing marker"
          />
        </label>
      )}
      {method !== "preserve" && (
        <>
          <fieldset className="imputation-groups" disabled={disabled}>
            <legend>Group by (up to five columns)</legend>
            {columns
              .filter((c) => c.column_name !== operation.column)
              .map((c) => (
                <label key={c.column_name}>
                  <input
                    type="checkbox"
                    aria-label={`Group ${operation.column} by ${c.column_name}`}
                    checked={groups.includes(c.column_name)}
                    disabled={
                      disabled ||
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
                  disabled={disabled}
                  value={String(operation.parameters.order_by || "")}
                  onChange={(e) => update({ order_by: e.target.value })}
                >
                  <option value="">Choose ordering column</option>
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
                    disabled={disabled}
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

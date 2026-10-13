import type { Operation } from "@/lib/types";
export function PercentageControls({
  operation,
  onChange,
  disabled,
}: {
  operation: Operation;
  onChange: (parameters: Record<string, unknown>) => void;
  disabled: boolean;
}) {
  function update(values: Record<string, unknown>) {
    onChange({ ...operation.parameters, ...values });
  }
  const advanced = (
    <div className="percentage-controls">
      <label className="setting">
        Percentage output
        <select
          aria-label={`Percentage format for ${operation.column}`}
          disabled={disabled}
          value={String(operation.parameters.format || "with_sign")}
          onChange={(e) => update({ format: e.target.value })}
        >
          <option value="with_sign">Include % (10%)</option>
          <option value="without_sign">No % — percentage points (10)</option>
          <option value="ratio">No % — fractional ratio (0.1)</option>
        </select>
      </label>
      <label className="setting">
        How should numbers without % be interpreted?
        <select
          aria-label={`Bare percentage interpretation for ${operation.column}`}
          disabled={disabled}
          value={String(operation.parameters.bare_interpretation || "preserve")}
          onChange={(e) => update({ bare_interpretation: e.target.value })}
        >
          <option value="preserve">Preserve bare numbers unchanged</option>
          <option value="percentage_points">
            Percentage points: 10 means 10%
          </option>
          <option value="fraction">Fractional ratios: 0.1 means 10%</option>
        </select>
      </label>
      <p className="currency-note">
        A % sign changes the meaning: 10% = 0.1, not 10. Bare numbers stay
        unchanged until you choose their interpretation. Invalid values and
        missing cells are preserved.
      </p>
    </div>
  );
  return (
    <div className="percentage-controls">
      <label className="setting">
        Percentage mark handling
        <select
          aria-label={`Percentage action for ${operation.column}`}
          disabled={disabled}
          value={String(operation.parameters.action || "preserve")}
          onChange={(e) => update({ action: e.target.value })}
        >
          <option value="preserve">No change</option>
          <option value="add">Add % to all numbers</option>
          <option value="remove">Remove % from all numbers</option>
          <option value="legacy">Advanced: rescale percentages / ratios</option>
        </select>
      </label>
      {operation.parameters.action === "legacy" ? (
        advanced
      ) : (
        <p className="currency-note">
          This changes the mark only: 10%, 20 and 0.2 become 10%, 20% and 0.2%
          when you add %. Removing it produces 10, 20 and 0.2. Numbers are not
          multiplied or divided. Missing and invalid values stay unchanged.
        </p>
      )}
    </div>
  );
}

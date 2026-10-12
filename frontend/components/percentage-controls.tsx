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
  return (
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
}

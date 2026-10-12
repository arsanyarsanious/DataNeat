import type { Operation } from "@/lib/types";
export function SymbolControls({
  operation,
  onChange,
  disabled,
  advanced,
}: {
  operation: Operation;
  onChange: (parameters: Record<string, unknown>) => void;
  disabled: boolean;
  advanced?: React.ReactNode;
}) {
  const action = String(operation.parameters.action || "preserve");
  function update(values: Record<string, unknown>) {
    onChange({ ...operation.parameters, ...values });
  }
  return (
    <div className="symbol-controls">
      <label className="setting">
        Symbol handling
        <select
          aria-label={`Symbol action for ${operation.column}`}
          disabled={disabled}
          value={action}
          onChange={(e) => update({ action: e.target.value })}
        >
          <option value="preserve">No change</option>
          <option value="add">Add the chosen symbol to all numbers</option>
          <option value="remove">
            Remove all symbols / labels from numbers
          </option>
          {advanced && (
            <option value="legacy">Advanced currency-aware formatting</option>
          )}
        </select>
      </label>
      {action === "add" && (
        <>
          <label className="setting">
            Symbol or label to add
            <input
              aria-label={`Symbol for ${operation.column}`}
              disabled={disabled}
              value={String(operation.parameters.symbol || "")}
              placeholder="e.g. $, USD, €, kg"
              maxLength={12}
              onChange={(e) => update({ symbol: e.target.value })}
            />
          </label>
          <label className="setting">
            Position
            <select
              aria-label={`Symbol position for ${operation.column}`}
              disabled={disabled}
              value={String(operation.parameters.position || "prefix")}
              onChange={(e) => update({ position: e.target.value })}
            >
              <option value="prefix">Before every number ($100)</option>
              <option value="suffix">After every number (100$)</option>
            </select>
          </label>
        </>
      )}
      {action === "legacy" ? (
        advanced
      ) : (
        <p className="currency-note">
          Add replaces existing labels on all recognized numeric values; remove
          strips them all. Numeric digits and scale are preserved. This does not
          convert currencies or units. Different currency/unit labels will be
          lost if you remove or replace them. Missing and unsupported values
          stay unchanged.
        </p>
      )}
    </div>
  );
}

import type { Operation } from "@/lib/types";
const countries = [
  ["EG", "Egypt (+20)"],
  ["US", "United States (+1)"],
  ["CA", "Canada (+1)"],
  ["GB", "United Kingdom (+44)"],
  ["SA", "Saudi Arabia (+966)"],
  ["AE", "United Arab Emirates (+971)"],
  ["IN", "India (+91)"],
  ["DE", "Germany (+49)"],
  ["FR", "France (+33)"],
  ["AU", "Australia (+61)"],
  ["IT", "Italy (+39)"],
];
export function PhoneControls({
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
    <div className="phone-controls">
      <label className="setting">
        Country codes and +
        <select
          aria-label={`Phone action for ${operation.column}`}
          disabled={disabled}
          value={String(operation.parameters.action || "preserve")}
          onChange={(e) => update({ action: e.target.value })}
        >
          <option value="preserve">No change</option>
          <option value="international">
            Add country codes and + to all numbers
          </option>
          <option value="international_digits">
            Add country codes to all numbers without +
          </option>
          <option value="national">
            Remove country codes and + (local numbers)
          </option>
          <option value="remove_plus">Remove + only, keep country codes</option>
          <option value="add_plus">
            Add + to recognized international numbers
          </option>
        </select>
      </label>
      {operation.parameters.action !== "preserve" && (
        <>
          <label className="setting">
            Country for local / unprefixed numbers
            <select
              aria-label={`Phone country for ${operation.column}`}
              disabled={disabled}
              value={String(operation.parameters.region || "")}
              onChange={(e) => update({ region: e.target.value })}
            >
              <option value="">Choose country</option>
              {operation.parameters.region &&
              !countries.some(
                ([code]) => code === operation.parameters.region,
              ) ? (
                <option value={String(operation.parameters.region)}>
                  {String(operation.parameters.region)} (custom country)
                </option>
              ) : null}
              {countries.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="setting">
            Other country (two-letter ISO code)
            <input
              aria-label={`Other phone country for ${operation.column}`}
              disabled={disabled}
              maxLength={2}
              placeholder="e.g. BR"
              value={
                countries.some(([code]) => code === operation.parameters.region)
                  ? ""
                  : String(operation.parameters.region || "")
              }
              onChange={(e) => update({ region: e.target.value.toUpperCase() })}
            />
          </label>
        </>
      )}
      <p className="currency-note">
        Choose the country used by local numbers; existing explicit
        international country codes are preserved when adding codes. Removing
        country codes restores the country's local dialing prefix where
        applicable. Numbers remain text, including meaningful leading zeros.
        Invalid or unresolved numbers are preserved. Removing codes discards
        country information; these checks do not verify ownership or
        reachability.
      </p>
    </div>
  );
}

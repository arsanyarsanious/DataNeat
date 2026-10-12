import type { Operation } from "@/lib/types";
const currencies = [
  "USD",
  "EUR",
  "GBP",
  "EGP",
  "SAR",
  "AED",
  "CAD",
  "AUD",
  "JPY",
  "CNY",
  "INR",
  "CHF",
  "NZD",
  "ZAR",
  "KWD",
  "QAR",
  "BHD",
  "OMR",
  "TRY",
  "SEK",
  "NOK",
  "DKK",
  "BRL",
  "MXN",
  "SGD",
  "HKD",
  "KRW",
];
export function CurrencyControls({
  operation,
  onChange,
  disabled,
}: {
  operation: Operation;
  onChange: (parameters: Record<string, unknown>) => void;
  disabled: boolean;
}) {
  const currency = String(operation.parameters.currency || ""),
    format = String(operation.parameters.format || "code");
  const aliases = (operation.parameters.symbol_aliases || []) as string[];
  const dollar = ["USD", "CAD", "AUD", "NZD", "SGD", "HKD"].includes(currency),
    yen = ["JPY", "CNY"].includes(currency);
  function update(values: Record<string, unknown>) {
    onChange({ ...operation.parameters, ...values });
  }
  return (
    <div className="currency-controls">
      <div className="currency-settings">
        <label className="setting">
          Intended currency
          <select
            disabled={disabled}
            aria-label={`Currency for ${operation.column}`}
            value={currency}
            onChange={(e) =>
              update({
                currency: e.target.value,
                symbol_aliases: [],
                assume_unlabelled: false,
                format: "code",
              })
            }
          >
            <option value="">Choose currency</option>
            {currencies.map((code) => (
              <option key={code}>{code}</option>
            ))}
          </select>
        </label>
        <label className="setting">
          Output notation
          <select
            disabled={disabled}
            aria-label={`Currency format for ${operation.column}`}
            value={format}
            onChange={(e) => update({ format: e.target.value })}
          >
            <option value="code">Currency code (USD 100)</option>
            <option value="number">Numbers only (100)</option>
            {["USD", "EUR", "GBP"].includes(currency) && (
              <option value="symbol">
                Currency symbol ($100 / €100 / £100)
              </option>
            )}
          </select>
        </label>
      </div>
      <label className="assumption-check">
        <input
          type="checkbox"
          disabled={disabled || !currency}
          checked={operation.parameters.assume_unlabelled === true}
          aria-label={`Assume bare amounts are ${currency || "selected currency"} in ${operation.column}`}
          onChange={(e) => update({ assume_unlabelled: e.target.checked })}
        />
        I confirm that amounts without a currency label are{" "}
        {currency || "in the selected currency"}.
      </label>
      {(dollar || yen) && (
        <label className="assumption-check">
          <input
            type="checkbox"
            disabled={disabled}
            aria-label={`Assign ${dollar ? "$" : "¥"} to ${currency} in ${operation.column}`}
            checked={aliases.includes(dollar ? "$" : "¥")}
            onChange={(e) =>
              update({
                symbol_aliases: e.target.checked ? [dollar ? "$" : "¥"] : [],
              })
            }
          />
          I confirm that {dollar ? "$" : "¥"} means {currency} in this column.
        </label>
      )}
      <p className="currency-note">
        No currency conversion is performed. Unconfirmed bare amounts, ambiguous
        symbols, invalid values, and other currencies keep their original
        values.
      </p>
    </div>
  );
}

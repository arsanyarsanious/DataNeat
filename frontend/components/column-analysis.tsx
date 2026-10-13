"use client";
import { useState } from "react";
import { CheckCheck, AlertTriangle } from "lucide-react";
import type { Column } from "@/lib/types";
const names: Record<string, string> = {
  invalid_dates: "Invalid dates",
  ambiguous_dates: "Dates with two possible meanings",
  currency_inconsistency: "Mixed currency notation",
  percentage_inconsistency: "Mixed percentage notation",
  phone_inconsistency: "Mixed country codes and + notation",
  invalid_phone: "Unrecognized phone numbers",
  symbol_inconsistency: "Mixed numeric symbols or labels",
  missing_values: "Missing values",
  extra_whitespace: "Extra whitespace",
  case_inconsistency: "Inconsistent capitalization",
  type_mismatch: "Values that do not match this column’s type",
};
export function ColumnAnalysis({
  columns,
  compact = false,
}: {
  columns: Column[];
  compact?: boolean;
}) {
  const [order, setOrder] = useState("alphabetical");
  const sorted =
    order === "alphabetical"
      ? [...columns].sort((a, b) =>
          a.column_name.localeCompare(b.column_name, undefined, {
            numeric: true,
          }),
        )
      : order === "reverse"
        ? [...columns].reverse()
        : [...columns];
  const problem = sorted.filter((c) => c.issues.length),
    healthy = sorted.filter((c) => !c.issues.length);
  function renderColumn(c: Column) {
    return (
      <section
        key={c.column_name}
        className="column-card"
        aria-label={`Analysis for column ${c.column_name}`}
      >
        <div className="column-section-heading">
          <div>
            <span className="column-caption">COLUMN</span>
            <h3>{c.column_name}</h3>
          </div>
          <span className={c.issues.length ? "count-badge" : "type-tag"}>
            {c.issues.length
              ? `${c.issues.length} issue categories`
              : "No issues detected"}
          </span>
        </div>
        <div className="column-meta">
          <span>Detected type: {c.detected_type}</span>
          {!compact && (
            <>
              <span>{Math.round(c.match_score * 100)}% valid type match</span>
              <span>{c.unique_count} unique values</span>
            </>
          )}
        </div>
        {c.issues.map((issue) => (
          <div key={issue.issue} className="column-issue">
            <div className="issue-row">
              <strong>
                {names[issue.issue] || issue.issue.replaceAll("_", " ")}
              </strong>
              <span className="count-badge">
                {issue.count} rows
                {issue.conflicting_categories
                  ? ` / ${issue.conflicting_categories} categories`
                  : ""}
              </span>
            </div>
            {issue.issue === "missing_values" && c.imputation && (
              <div>
                <p>
                  {c.missing_count} missing cells ({c.missing_percentage}%).
                  Suggested imputation: {c.imputation.method}.{" "}
                  {c.imputation.explanation}
                </p>
                <p>
                  Imputation is optional. Review methods, grouping, ordering,
                  and assumptions in the cleaning plan. Missing percentage alone
                  does not establish random missingness.
                </p>
              </div>
            )}
            {issue.issue === "invalid_dates" && (
              <p>
                These values cannot be parsed as real calendar dates. In the
                cleaning plan, leave them unchanged, replace them with empty
                cells, or enter corrected dates for individual rows.
              </p>
            )}
            {issue.issue === "ambiguous_dates" && (
              <p>
                These dates could mean day/month or month/day. They stay
                unchanged until you confirm an interpretation.
              </p>
            )}
            {(issue.issue === "phone_inconsistency" ||
              issue.issue === "symbol_inconsistency") && (
              <>
                <p>
                  {issue.issue === "phone_inconsistency"
                    ? "Country codes, +, 00 prefixes, and local numbers are mixed. Choose a country and the format you want in the cleaning plan."
                    : "Some numeric values have a symbol or label and others do not. Add a chosen symbol to every number, remove all labels, or make no change."}
                </p>
                <div className="format-chips">
                  {Object.entries(issue.formats || {}).map(
                    ([format, count]) => (
                      <span key={format}>
                        {format}: {count} rows
                      </span>
                    ),
                  )}
                </div>
                {issue.country_codes && (
                  <p>
                    Detected country codes:{" "}
                    {Object.entries(issue.country_codes)
                      .map(([code, count]) => `+${code}: ${count} rows`)
                      .join(" · ")}
                  </p>
                )}
              </>
            )}
            {issue.issue === "invalid_phone" && (
              <p>
                These values could not be recognized as phone numbers. They are
                preserved rather than guessed or deleted.
              </p>
            )}
            {issue.issue === "percentage_inconsistency" && (
              <>
                <p>
                  Some values include % and others do not. Choose a consistent
                  output and confirm whether bare numbers are percentage points
                  or fractional ratios.
                </p>
                <div className="format-chips">
                  {Object.entries(issue.formats || {}).map(
                    ([format, count]) => (
                      <span key={format}>
                        {format}: {count} rows
                      </span>
                    ),
                  )}
                </div>
              </>
            )}
            {issue.issue === "currency_inconsistency" && (
              <>
                <p>
                  Some amounts use different currency labels or comma
                  formatting. Choose whether to include a currency symbol and
                  thousands separators for all recognized amounts in the
                  cleaning plan.
                </p>
                <div className="format-chips">
                  {Object.entries(issue.formats || {}).map(
                    ([format, count]) => (
                      <span key={format}>
                        {format}: {count} rows
                      </span>
                    ),
                  )}
                </div>
              </>
            )}
            {issue.examples.length > 0 && (
              <div className="issue-examples">
                <span>Examples</span>
                {issue.examples.map((value, index) => (
                  <code key={index}>{value}</code>
                ))}
              </div>
            )}
          </div>
        ))}
        {c.date_analysis && (
          <div className="date-evidence">
            <strong>Date interpretation evidence</strong>
            <p>
              Day-first evidence: {c.date_analysis.dd_mm_evidence} ·
              Month-first: {c.date_analysis.mm_dd_evidence}
            </p>
            {c.date_analysis.conflicting_evidence && (
              <p className="warning-text">
                <AlertTriangle size={13} />
                Conflicting date formats. Confirm ambiguous dates carefully.
              </p>
            )}
          </div>
        )}
        {!c.issues.length && !compact && (
          <div className="column-samples">
            {c.sample_values.map((value, index) => (
              <span key={index}>{String(value)}</span>
            ))}
          </div>
        )}
      </section>
    );
  }
  return (
    <div className="column-analysis">
      <div className="analysis-section-heading">
        <h2>{compact ? "Remaining issues by column" : "Issues by column"}</h2>
        <p>{problem.length} columns need attention.</p>
      </div>
      <label className="setting">
        Sort columns
        <select
          aria-label="Sort analysis columns"
          value={order}
          onChange={(e) => setOrder(e.target.value)}
        >
          <option value="alphabetical">Column name (A–Z)</option>
          <option value="position">Column position (left to right)</option>
          <option value="reverse">Column position (right to left)</option>
        </select>
      </label>
      {problem.length ? (
        problem.map(renderColumn)
      ) : (
        <div className="notice">
          <CheckCheck size={18} />
          No column issues detected.
        </div>
      )}
      {!compact && healthy.length > 0 && (
        <details className="healthy-columns">
          <summary>Columns with no detected issues ({healthy.length})</summary>
          <div>{healthy.map(renderColumn)}</div>
        </details>
      )}
    </div>
  );
}

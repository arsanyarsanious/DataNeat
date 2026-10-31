import type { Column, ImputationReadiness } from "./types";

const labels: Record<string, string> = {
  missing_marker: "Unresolved missing-value labels",
  extra_whitespace: "Extra whitespace",
  case_inconsistency: "Inconsistent capitalization",
  invalid_dates: "Invalid dates",
  ambiguous_dates: "Ambiguous dates",
  date_format_inconsistency: "Mixed date formats",
  type_mismatch: "Values with the wrong type",
  odd_value: "Values unlike the rest of the column",
  invalid_email: "Invalid email addresses",
  invalid_phone: "Unrecognized phone numbers",
  boolean_inconsistency: "Inconsistent boolean labels",
  currency_inconsistency: "Mixed currency notation",
  percentage_inconsistency: "Mixed percentage notation",
  symbol_inconsistency: "Mixed numeric symbols or labels",
  phone_inconsistency: "Mixed phone notation",
  duplicate: "Duplicate rows",
  duplicate_rows: "Duplicate rows",
  outlier: "Outliers awaiting review",
  rule_negative: "Negative values not allowed",
  invalid_data_format: "Invalid data format",
  data_format: "Data format interpretation",
  invalid_time: "Invalid clock times",
  time_format: "Mixed clock formats",
  invalid_duration: "Invalid durations",
  duration_format: "Mixed duration formats",
};

export function getImputationReadiness(column?: Column): ImputationReadiness {
  if (!column) return { ready: false, blocking_count: 0, blocking_issues: [], message: "Choose a column before filling missing values." };
  if (column.imputation_readiness) return column.imputation_readiness;

  // Upload profiles can precede the current workflow's authoritative readiness.
  const blocking_issues = column.issues
    .filter(issue => issue.count > 0 && !["missing", "missing_values", "rule_required"].includes(issue.issue))
    .map(issue => ({
      kind: issue.issue,
      label: labels[issue.issue] || issue.issue.replaceAll("_", " "),
      count: issue.count,
      example_rows: (issue.row_indices || []).slice(0, 3).map(row => row + 2),
    }));
  if (column.missing_marker_review?.count && !blocking_issues.some(issue => issue.kind === "missing_marker")) {
    blocking_issues.push({ kind: "missing_marker", label: labels.missing_marker, count: column.missing_marker_review.count, example_rows: [] });
  }
  const blocking_count = blocking_issues.reduce((sum, issue) => sum + issue.count, 0);
  return {
    ready: !blocking_count,
    blocking_count,
    blocking_issues,
    message: blocking_count
      ? `Resolve the other issues in column "${column.column_name}" before filling missing values. Correct or clear invalid values, and review the remaining flagged values first.`
      : "Only missing values remain, so this column is ready for imputation.",
  };
}

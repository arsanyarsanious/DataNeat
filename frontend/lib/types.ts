export type Issue = {
  issue: string;
  column: string;
  count: number;
  examples: string[];
  conflicting_categories?: number;
  formats?: Record<string, number>;
  country_codes?: Record<string, number>;
};
export type DateAnalysis = {
  patterns: Record<string, number>;
  ambiguous_count: number;
  ambiguous_examples: string[];
  invalid_count: number;
  invalid_examples: string[];
  dd_mm_evidence: number;
  mm_dd_evidence: number;
  conflicting_evidence: boolean;
  suggested_interpretation: string | null;
};
export type Column = {
  column_name: string;
  detected_type: string;
  match_score: number;
  total_rows: number;
  missing_count: number;
  missing_percentage: number;
  unique_count: number;
  pandas_dtype: string;
  sample_values: unknown[];
  issues: Issue[];
  date_analysis?: DateAnalysis;
};
export type Profile = {
  rows: number;
  columns_count: number;
  missing_count: number;
  duplicate_rows: number;
  issue_count: number;
  columns: Column[];
};
export type Preview = {
  columns: string[];
  rows: unknown[][];
  total_rows: number;
  page: number;
  page_size: number;
};
export type Operation = {
  id: string;
  column: string | null;
  operation: string;
  issue: string;
  parameters: Record<string, unknown>;
  affected_rows: number;
  explanation: string;
  safety: "safe" | "review" | "destructive";
  requires_confirmation: boolean;
  enabled: boolean;
};
export type Upload = {
  file_id: string;
  filename: string;
  metadata: {
    sheets: string[];
    worksheet?: string;
    encoding?: string;
    delimiter?: string;
    header_adjustments: { original: string; name: string }[];
  };
  preview: Preview;
  profile: Profile;
  plan: Operation[];
};
export type Log = {
  id: string;
  operation: string;
  column: string | null;
  modified_values: number;
  removed_rows: number;
  parameters: Record<string, unknown>;
  status: string;
};
export type Validation = {
  rows_before: number;
  rows_after: number;
  missing_before: number;
  missing_after: number;
  duplicates_removed: number;
  dates_standardized: number;
  numeric_values_standardized: number;
  text_values_modified: number;
  modified_values: number;
  unresolved_issues: number;
  remaining_issues: Issue[];
  before: Profile;
  after: Profile;
};
export type Results = {
  preview: Preview;
  validation: Validation;
  operations: Log[];
  filename: string;
  cleaned_at: string;
};
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: "same-origin",
  });
  const body = await response.json();
  if (!response.ok) {
    const message =
      typeof body.detail === "string"
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail
              .map((item: { msg: string }) =>
                item.msg.replace(/^Value error, /, ""),
              )
              .join("; ")
          : "Request failed. Check your settings and retry.";
    throw new Error(message);
  }
  return body;
}

export type InvalidDateRows = {
  rows: { row_index: number; spreadsheet_row: number; value: unknown }[];
  total: number;
  page: number;
  page_size: number;
};

// Share one bootstrap request so simultaneous first requests cannot replace the session cookie.
let sessionBootstrap: Promise<{ max_upload_mb: number }> | null = null;
export function initializeSession() {
  if (!sessionBootstrap)
    sessionBootstrap = api<{ max_upload_mb: number }>("/health").catch(
      (error) => {
        sessionBootstrap = null;
        throw error;
      },
    );
  return sessionBootstrap;
}

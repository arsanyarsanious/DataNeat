import type { Profile } from "./types";

const STORAGE_KEY = "dataneat-cleaning-choices-v1";
const MAX_CHOICES = 20;
const MAX_STEPS = 100;
const DATE_FORMATS = ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY/MM/DD", "DD-MM-YYYY", "MM-DD-YYYY"];
export type ReusableAction = "trim_whitespace" | "normalize_boolean" | "normalize_capitalization" | "normalize_dates" | "normalize_time" | "normalize_duration";
export type ReusableStep = { column: string; action: ReusableAction; parameters: Record<string, string | boolean> };
export type CleaningDecision = { kind: "fix"; body: { column: string; action: string; scope: "column"; parameters?: Record<string, unknown>; revision?: number; row_index?: number; confirmed?: boolean } };
export type ReusableChoice = { version: 1; id: string; name: string; createdAt: string; source_columns: string[]; steps: ReusableStep[] };
export type ChoiceCompatibility = { steps: CleaningDecision[]; warnings: string[]; skipped: number };
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const columnName = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 512 && !/[\u0000-\u001f\u007f]/.test(value);

// Persist only transferable notation settings. Cell values, row references,
// accepted findings, replacements and input-date judgments never reach storage.
function cleanStep(value: unknown, decision: boolean): ReusableStep | null {
  if (!record(value)) return null;
  const body = decision ? value.kind === "fix" && record(value.body) ? value.body : null : value;
  if (!body || decision && body.scope !== "column" || !columnName(body.column)) return null;
  const parameters = record(body.parameters) ? body.parameters : {};
  const result: ReusableStep = { column: body.column, action: body.action as ReusableAction, parameters: {} };
  switch (body.action) {
    case "trim_whitespace": break;
    case "normalize_boolean": {
      const format = parameters.format ?? "true_false";
      if (!["true_false", "yes_no", "one_zero"].includes(String(format))) return null;
      result.parameters.format = String(format); break;
    }
    case "normalize_capitalization": {
      if (!["title", "upper", "lower"].includes(String(parameters.strategy))) return null;
      result.parameters.strategy = String(parameters.strategy); break;
    }
    case "normalize_dates": {
      if (parameters.interpretation && parameters.interpretation !== "preserve") return null;
      const output = parameters.output_format ?? "YYYY-MM-DD";
      if (!DATE_FORMATS.includes(String(output)) || parameters.include_time !== undefined && typeof parameters.include_time !== "boolean") return null;
      result.parameters = { interpretation: "preserve", output_format: String(output), include_time: parameters.include_time === true }; break;
    }
    case "normalize_time": {
      const format = parameters.format ?? "24_hour";
      if (!["24_hour", "12_hour"].includes(String(format))) return null;
      result.parameters.format = String(format); break;
    }
    case "normalize_duration": break;
    default: return null;
  }
  return result;
}

export function sanitizeReusableDecisions(decisions: unknown[]): ReusableStep[] {
  return decisions.slice(0, MAX_STEPS).map(step => cleanStep(step, true)).filter((step): step is ReusableStep => step !== null);
}

function cleanChoice(value: unknown): ReusableChoice | null {
  if (!record(value) || value.version !== 1 || typeof value.id !== "string" || !/^[\w-]{1,80}$/.test(value.id) || typeof value.name !== "string" || !value.name.trim() || value.name.length > 80 || !Array.isArray(value.steps) || value.steps.length > MAX_STEPS) return null;
  const steps = value.steps.map(step => cleanStep(step, false)).filter((step): step is ReusableStep => step !== null);
  if (!steps.length) return null;
  return { version: 1, id: value.id, name: value.name.trim(), createdAt: typeof value.createdAt === "string" ? value.createdAt.slice(0, 40) : "", source_columns: Array.isArray(value.source_columns) ? value.source_columns.filter(columnName).slice(0, 200) : [...new Set(steps.map(step => step.column))], steps };
}

export function readReusableChoices(): { choices: ReusableChoice[]; warning: string } {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return { choices: [], warning: "" };
    if (stored.length > 1_000_000) return { choices: [], warning: "Saved choices are too large to read. You can create new choices." };
    const value: unknown = JSON.parse(stored);
    if (!Array.isArray(value)) throw new Error("Invalid saved choices");
    const choices = value.slice(0, MAX_CHOICES).map(cleanChoice).filter((choice): choice is ReusableChoice => choice !== null);
    return { choices, warning: choices.length !== value.length ? "Some unsupported saved choices were ignored. Your spreadsheet has not changed." : "" };
  } catch {
    return { choices: [], warning: "This browser could not read saved choices. You can still review suggested fixes." };
  }
}

export function saveReusableChoice(name: string, decisions: unknown[], sourceColumns: string[]): ReusableChoice[] {
  const trimmed = name.trim();
  if (!trimmed || trimmed.length > 80) throw new Error("Give these choices a name of 1–80 characters.");
  if (decisions.length > MAX_STEPS) throw new Error("Save up to 100 column actions at a time. Deselect some columns before saving.");
  const steps = sanitizeReusableDecisions(decisions);
  if (!steps.length) throw new Error("These actions cannot be saved as reusable choices.");
  const current = readReusableChoices().choices;
  const matching = current.find(choice => choice.name.toLocaleLowerCase() === trimmed.toLocaleLowerCase());
  if (!matching && current.length >= MAX_CHOICES) throw new Error("You have 20 saved choices. Delete an unused choice before saving another.");
  const next: ReusableChoice = { version: 1, id: matching?.id || crypto.randomUUID(), name: trimmed, createdAt: new Date().toISOString(), source_columns: sourceColumns.filter(columnName).slice(0, 200), steps };
  const choices = [next, ...current.filter(choice => choice.id !== next.id)];
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(choices)); } catch { throw new Error("This browser could not save your choices. Your spreadsheet is unchanged."); }
  return choices;
}

export function deleteReusableChoice(id: string): ReusableChoice[] {
  const choices = readReusableChoices().choices.filter(choice => choice.id !== id);
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(choices)); } catch { throw new Error("This browser could not delete the saved choice."); }
  return choices;
}

export function compatibleReusableChoice(choice: ReusableChoice, profile: Profile, declaredIdentifiers: string[] = [], protectedColumns: string[] = []): ChoiceCompatibility {
  const warnings: string[] = [], steps: CleaningDecision[] = [];
  const typeMap: Partial<Record<ReusableAction, string[]>> = { normalize_boolean: ["boolean"], normalize_capitalization: ["text", "category", "categorical"], normalize_dates: ["date", "datetime"], normalize_time: ["time"], normalize_duration: ["duration"] };
  for (const step of choice.steps) {
    const column = profile.columns.find(item => item.column_name === step.column);
    let reason = "";
    if (!column) reason = "column is absent";
    else if (column.detected_type === "identifier" || declaredIdentifiers.includes(step.column)) reason = "identifier is protected";
    else if (protectedColumns.includes(step.column)) reason = "existing user-entered corrections are protected";
    else if ((column.missing_marker_review?.count || 0) > 0) reason = "missing-value labels need review";
    else if (typeMap[step.action] && !typeMap[step.action]!.includes(column.detected_type)) reason = `current type is ${column.detected_type}`;
    if (reason) { warnings.push(`${step.column}: skipped because ${reason}.`); continue; }
    steps.push({ kind: "fix", body: { column: step.column, scope: "column", action: step.action, parameters: { ...step.parameters } } });
  }
  return { steps, warnings: [...new Set(warnings)], skipped: choice.steps.length - steps.length };
}

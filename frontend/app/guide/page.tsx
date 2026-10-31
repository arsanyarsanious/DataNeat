"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, BookOpen, CheckCircle2, Search, ShieldCheck, X } from "lucide-react";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import "./guide.css";

type GuideSection = {
  id: string;
  title: string;
  summary: string;
  keywords?: string;
  items: { title: string; text: string }[];
  note?: string;
  related?: { id: string; label: string }[];
};

const sections: GuideSection[] = [
  {
    id: "quick-start", title: "Start with your first file",
    summary: "DataNeat helps you find inconsistent values, choose corrections, and download a cleaned table with a readable record of your decisions.",
    keywords: "upload begin login csv xlsx excel analysis quickstart getting started",
    items: [
      { title: "1. Upload", text: "Choose Begin cleaning, continue through the login page, then upload a CSV or XLSX file. For an Excel workbook, select the worksheet you want to clean. When accounts are not configured, choose Continue to local workspace." },
      { title: "2. Explore", text: "See a preview and real counts from your uploaded data, then choose how to clean. Clean manually opens the interactive sheet. Clean automatically asks a short optional questionnaire. Both paths use the same working copy, so you can switch to Automatic cleaning from the sheet without starting over." },
      { title: "3. Review", text: "Check the suggested fixes, follow Guided cleaning, or open a highlighted cell. Choose the correction first, then its scope. Review the proposed result before applying it." },
      { title: "4. Export", text: "See what changed and what still needs attention, then prepare Excel, CSV, or a PDF report. Excel exports contain only the selected worksheet as a data table. Other sheets, workbook formatting, charts and executable formulas are not preserved. Your original upload is preserved separately." },
    ],
    note: "An issue flag is a reason to review a value. It does not always mean the value is wrong.",
    related: [{ id: "faster-cleaning", label: "Ways to finish with fewer steps" }, { id: "missing-labels", label: "Decide what NA and null mean" }],
  },
  {
    id: "faster-cleaning", title: "Clean with fewer steps",
    summary: "Use one review for related corrections, or work through one decision at a time.",
    keywords: "suggested fixes combined preview bulk guided cleaning next progress completion reusable saved choices more options",
    items: [
      { title: "Review suggested fixes together", text: "Review the proposed corrections in one place, choose the ones you want, and inspect the combined preview before applying the selection. Nothing changes merely because a suggestion appears." },
      { title: "Solve a whole issue type", text: "When a correction supports it, choose all cells with the same issue in the selected column. For example, clear or replace all invalid dates in one command even when their text is different. Other corrections can target the same value or all eligible column values." },
      { title: "Guided cleaning", text: "Focus on one issue type at a time. Open its correction, fix it, or skip it for this review. The guide keeps the next decision visible so you do not need to search the entire sheet." },
      { title: "More options when you need them", text: "The main correction appears first. Open More options for additional controls instead of working through every setting for a simple fix. You still choose where the correction applies." },
      { title: "Reuse reviewed choices", text: "Save automatic-cleaning choices for a similar file, load them, and review them before starting. For a fuller repeatable process, use Recipes. Reusing choices is optional; it does not silently apply them to a new upload." },
      { title: "A clear finishing point", text: "Review & export shows the work completed and remaining issues. You can export after reviewing the remaining findings; a flag is not necessarily an error that must be removed." },
    ],
    related: [{ id: "automatic", label: "Automatic cleaning and exceptions" }, { id: "recipes-batch", label: "Recipes and batch processing" }],
  },
  {
    id: "sheet", title: "Find and fix issues in the sheet",
    summary: "Column counts cover the whole file, including rows outside the visible part of the sheet.",
    keywords: "search ctrl f cmd f scroll column issues first next highlight filter tooltip scope manual",
    items: [
      { title: "Navigate by column and issue", text: "Choose a column's issue count to see the issue types present in that column. First issue starts the review. Next Issue moves to a different issue type and stops at the last type. Fix this issue opens the correction panel." },
      { title: "Search the entire file", text: "Use the application's Search or Ctrl/Cmd+F. Search can be restricted to a column. The sheet scrolls continuously and loads rows as needed; the browser's own page search cannot inspect unloaded rows." },
      { title: "Choose what, then where", text: "Open a cell and choose a correction. Inspect its example and count, then select This cell, matching values, the same issue, or eligible cells in the column where offered. Apply change commits the reviewed correction." },
      { title: "Accept a legitimate value", text: "Use This value is correct for a finding you have checked. User-entered replacement values and constants are accepted for the cells changed. Statistical estimates remain marked and are not treated as verified observations." },
      { title: "Understand a disabled Apply button", text: "A blocking error identifies what must be resolved before applying. A true no-change result also explains why there is nothing to apply. Confirming an ambiguous date's interpretation can still be a valid decision even when the displayed text stays the same." },
    ],
    related: [{ id: "history", label: "Undo a decision" }, { id: "dates-time", label: "Date interpretation and output" }],
  },
  {
    id: "missing-labels", title: "Empty cells, missing labels, and preparation",
    summary: "Your sheet starts as uploaded. DataNeat asks before treating text such as NA as an empty cell.",
    keywords: "n/a na null none blank empty missing whitespace trim preparation convert labels keep text",
    items: [
      { title: "Actual blanks versus text", text: "A blank cell or actual null is missing. Text such as NA, N/A, null, empty, none, or a dash stays as written until you choose Convert labels to empty or Keep as text for that column. A label can be a valid category in your data." },
      { title: "Resolve labels before filling gaps", text: "If you want imputation to fill an NA label, first confirm that the label means missing. Automatic cleaning leaves columns with an unresolved label decision unchanged and explains why." },
      { title: "Trim and other preparation", text: "Extra-whitespace issues suggest Trim first. Tools → Preparation also offers leading/trailing trim, a separate choice to collapse repeated internal spaces, custom missing-marker lists, and column exceptions. Review the proposal before applying." },
    ],
    note: "Changing preparation settings does not reverse an earlier conversion. Undo that recorded step if you need the original values back.",
    related: [{ id: "imputation", label: "Fill missing values" }],
  },
  {
    id: "automatic", title: "Automatic cleaning and column exceptions",
    summary: "Answer the optional questionnaire once and apply those policies to the current working copy.",
    keywords: "survey automatic cleaning exceptions title upper lower yes no duplicates remove rows saved choices",
    items: [
      { title: "Choose your policies", text: "The survey covers trimming, boolean labels, capitalization, date interpretation and output, missing numeric measurements, and exact duplicate rows. Keep values unchanged wherever you do not want a transformation. Duplicate removal keeps the first copy of a full duplicate row." },
      { title: "Add exceptions", text: "A default policy can have different choices for individual columns. For example, use Title for city names and lower for another text column. Duplicate-row removal is a file-level choice." },
      { title: "Continue from manual work", text: "The Automatic cleaning button is available inside the interactive sheet. Opening or cancelling the questionnaire preserves your existing edits. Starting the run applies your chosen policies; you do not confirm each cell separately." },
      { title: "Review what was preserved", text: "Identifiers, columns with accepted manual corrections, and unresolved missing-label columns are protected from automatic changes. Ambiguous units, invalid values, complex estimates, and record merges require their own review. Automatic cleaning does not run every advanced converter." },
      { title: "Filling waits until the column is ready", text: "Automatic cleaning fills missing numeric values only after other findings in that target column have been resolved. If a column still has another issue, its fill is skipped and the result explains the reason. Correct, clear, or accept the remaining values before trying the fill again." },
    ],
    related: [{ id: "history", label: "Undo an automatic run" }, { id: "recipes-batch", label: "Reuse choices on another file" }],
  },
  {
    id: "text-numbers", title: "Text, booleans, numbers, and column rules",
    summary: "Standardize representations while keeping the meaning of the column explicit.",
    keywords: "capitalization spelling cairo kairo unify mapping boolean currency percentage phone email negative temperature rules identifier",
    items: [
      { title: "Text and equivalent spellings", text: "Trim whitespace, choose Title / UPPER / lower, or use Unify text values to map selected spellings to a name you provide. Similar-spelling suggestions need your review; matching spellings does not prove two values mean the same thing." },
      { title: "Booleans", text: "Unify true/false, yes/no, y/n, and 1/0 into the representation you choose for the column." },
      { title: "Choose a column data type", text: "Open the three-dot Settings button in a column heading, then choose Column data type and Save data type. Your choice overrides the column name and automatic detection. Choose Text, Number, Salary, Serial / identifier, Phone, Email, Date, Date and time, Clock time, Duration, Location, Coordinates, Currency, Percentage, Boolean, URL or IP address. Values are unchanged. Auto restores detection; History can undo the choice. Serial / identifier protects leading zeros. Salary is an ordinary numeric amount and does not assign a currency." },
      { title: "Original Excel colors and formula results", text: "Original cell colors are hidden by default. Use Show original colors in Explore or Review to display solid fills; warning icons and colored edges still identify issues. This display preference does not modify data or preserve formatting in cleaned exports. Conditional formatting and non-solid fills are not reproduced. Formula cells show their last saved Excel results, not the formula expression. DataNeat does not recalculate formulas. If results are missing, open the workbook in Excel, recalculate, save and upload it again." },
      { title: "Amounts, percentages, and contact fields", text: "Standardize supported currency or percentage notation with an explicit interpretation for bare percentages. Currency conversion between exchange rates is not provided. Phone formatting may need country information. Email and phone checks validate form, not whether the address or number exists." },
      { title: "Odd values and negative values", text: "A text value among numbers, or a percentage among currency amounts, can be flagged for review. Negative values are allowed by default. Disallow them in Column settings or Column rules when the column requires it, then review removing the sign, clearing, or replacing them." },
      { title: "Tell DataNeat what is valid", text: "Set a column's intended type, identifier status, required or unique values, allowed labels, bounds, currency, percentage scale, or wildcard pattern. Rules flag findings; they do not rewrite data. Text identifiers and leading zeros should be preserved." },
    ],
    related: [{ id: "formats", label: "Additional supported formats" }, { id: "quality-tools", label: "Rules involving several columns" }],
  },
  {
    id: "dates-time", title: "Dates, clock times, and durations",
    summary: "Choose how input is interpreted separately from how the result is displayed.",
    keywords: "date day first month first dd/mm/yyyy slash dash am pm 12 hour 24 hour duration compound pt45m time",
    items: [
      { title: "Date input and output", text: "Choose Day first or Month first when an input such as 03/04/2024 could mean either date. Output choices include YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, YYYY/MM/DD, DD-MM-YYYY, and MM-DD-YYYY. Include time when needed. An impossible calendar date cannot be fixed just by changing its display format." },
      { title: "Clock time", text: "A time of day can use AM/PM or a 24-hour clock. Choose a 12-hour or 24-hour output. A clock time is different from an elapsed duration." },
      { title: "Elapsed duration", text: "Recognize forms such as PT45M, 45 min, 1 day 3 hours, or 1d3h30m15s and standardize them to elapsed HH:MM:SS. Hours can exceed 24 without wrapping. Compound English unit expressions are supported." },
      { title: "Date estimates and numeric timestamps", text: "Date median and verified date-pattern completion are available for missing dates. Unix and Excel serial dates need an explicit source format; timezone conversion needs explicit zone choices. These are separate from choosing slashes or dashes." },
    ],
    related: [{ id: "imputation", label: "Date median and pattern requirements" }, { id: "formats", label: "Serial dates and time zones" }],
  },
  {
    id: "imputation", title: "Fill missing values",
    summary: "Choose an estimate that fits your data. Filled values remain visibly marked as estimates.",
    keywords: "mean median mode forward backward fill interpolation date pattern group imputation statistical missing dotted estimate",
    items: [
      { title: "Resolve other issues first", text: "Before any missing-value fill, resolve every other issue in the selected target column. Correct an invalid value, clear it when appropriate, or explicitly accept a finding when the value is valid. Only missing cells may remain as unresolved findings. The fill stays blocked with a clear reason until the column is ready; selecting a constant or a different method does not bypass this check." },
      { title: "Simple and grouped methods", text: "Depending on the column type, choose a constant, Mean, Median, Mode, Forward fill, Backward fill, or Linear interpolation. Mean, Median, and Mode each have an optional grouping choice inside their settings. Group calculations use the observations in each group." },
      { title: "Ordered data", text: "Directional fills and interpolation need meaningful order and a group/entity choice, or confirmation that the rows are one series. The current methods fill interior gaps; leading or trailing gaps are left empty. Missing group keys and groups without enough valid evidence are explained." },
      { title: "Median for dates", text: "Date median estimates a chronological midpoint. Confirm that an estimated date is appropriate; date-only output has rounding choices, while timestamps retain time. Resolve invalid or ambiguous dates first." },
      { title: "Date-pattern completion", text: "Detect a fixed interval or calendar-month/year sequence, including month-end cases. Every original date must agree. The default requires at least three original dates and 60% original-date coverage of the series, with other coverage thresholds available. It fills only internal gaps. Business-day calendars, holidays, and arbitrary seasonal patterns are not inferred." },
      { title: "Protect observations", text: "Imputation does not overwrite observed target values. Earlier estimates are excluded from donor evidence. Dotted underlines identify estimated values; their method is retained in the audit and report." },
    ],
    related: [{ id: "model-imputation", label: "Estimate with related numeric columns" }],
  },
  {
    id: "model-imputation", title: "KNN and Iterative imputation",
    summary: "Use other numeric measurements to estimate a missing numeric target, with validation before applying.",
    keywords: "knn iterative machine learning model multivariate helpers mae validation baseline impute missing",
    items: [
      { title: "Where and what to select", text: "Open Tools → More cleaning tools → KNN & Iterative imputation. Choose one plain numeric target and one to eight related plain numeric helper columns. Identifiers, dates, booleans, unresolved missing labels, and unconverted labelled amounts are excluded." },
      { title: "Prepare the target column", text: "The same readiness rule applies here: resolve other issues in the target column before estimating its missing values. The tool explains any blocking findings rather than attempting an estimate from an unresolved target." },
      { title: "Choose and review the method", text: "KNN uses similar observed rows; Iterative estimates relationships between columns. Review the held-out error beside a median baseline. Validation can be unavailable with too few observations or worse than the baseline; a model is not automatically more accurate. Random holdout does not establish future forecasting accuracy." },
      { title: "Understand the limits", text: "The review uses up to 2,000 original fitting donors and 10,000 empty target cells per run. At least five original donors are required, or the selected KNN neighbor count when larger. Rows without usable helper evidence remain empty. Previously estimated values and user constants are excluded from training evidence." },
      { title: "Apply deliberately", text: "Review the proposal and acknowledge that the results are estimates. Original target observations stay intact, and filled values receive estimate underlines, history entries, and report details." },
    ],
    related: [{ id: "quality-tools", label: "Other reviewed quality tools" }],
  },
  {
    id: "quality-tools", title: "Related rules, similar records, and outliers",
    summary: "Open Tools → More cleaning tools for checks that need more context than a single cell.",
    keywords: "cross column rules total quantity price relationship conditional required fuzzy duplicate similar record merge outlier iqr mad cap winsorize",
    items: [
      { title: "Related column rules", text: "Compare two columns, check a calculation such as Total = Quantity × Price, or require a value when another column matches a condition. Add a named rule, check the draft, and save it to highlight exact rows and target columns. Saving a rule does not change values. Separately review arithmetic recalculation or clearing flagged targets; invalid operands are not guessed." },
      { title: "Similar records", text: "Choose two to five matching fields and a similarity threshold, with an optional exact blocking column. Review complete candidate records side by side. Keep both, or choose the surviving row and each conflicting field before reviewing the merge. No fuzzy match merges automatically. A similarity score is not a probability that two people or records are identical." },
      { title: "Candidate coverage", text: "Similar-record search is bounded to 20,000 compared pairs and shows up to 100 candidates. The review tells you when coverage is incomplete. Keeping both applies only while the complete records remain unchanged." },
      { title: "Outlier review", text: "Choose a plain numeric column, IQR or normalized MAD sensitivity, and optional grouping. Review the calculated bounds and flagged values. Save highlights, keep values as valid, convert them to empty, or explicitly cap them at the displayed bounds. At least five original observations per group are needed; a statistical outlier may still be correct." },
    ],
    note: "These tools use the current working copy and support History and Undo. Models, row merges, and reviewed row judgements require fresh review on a different dataset and are not transferable recipe steps.",
    related: [{ id: "model-imputation", label: "The fourth quality tool: KNN & Iterative" }, { id: "history", label: "Review and undo changes" }],
  },
  {
    id: "formats", title: "Other supported data formats",
    summary: "Specialized converters are available through column settings and appropriate cell corrections.",
    keywords: "localized number scientific arabic persian fraction units length mass volume kelvin celsius fahrenheit unix excel serial timezone dst json list coordinates latitude longitude dms url ip",
    items: [
      { title: "Localized numbers and fractions", text: "Choose dot-decimal, comma-decimal, or Arabic separator conventions explicitly when needed. Arabic/Persian digits, scientific notation, ASCII mixed fractions, and supported Unicode fractions can be normalized. A zero denominator is invalid." },
      { title: "Actual measurement conversion", text: "Convert compatible units of length, mass, volume, temperature, and duration. Choose the target unit and a source for unlabelled values. Incompatible dimensions and temperatures below absolute zero are rejected. This does not perform foreign-exchange conversion." },
      { title: "Numeric dates and time zones", text: "Select Unix seconds/milliseconds/microseconds or Excel 1900/1904 explicitly. Excel's fictitious serial 60 is rejected. Timezone conversion uses IANA zones; naive times require a source zone, nonexistent DST times are rejected, and repeated times need an explicit choice." },
      { title: "JSON and delimited lists", text: "Normalize strict JSON or quoted delimited lists, optionally trim or deduplicate items, and expand top-level keys or positions into new columns. The original column and row count are preserved. Nested structures remain JSON; this is not recursive flattening or array-to-row expansion." },
      { title: "Coordinates, URLs, and IP addresses", text: "Normalize explicitly ordered latitude/longitude or DMS coordinates with range checks. Validate and normalize HTTP/HTTPS URLs and IPv4/IPv6 notation. These checks do not geocode, browse a URL, query DNS, or prove a host is reachable." },
    ],
    note: "If an ambiguous source convention is required, choose it before applying. New format converters report the exact column, spreadsheet row, and value when a scoped conversion cannot be completed.",
  },
  {
    id: "history", title: "History, Undo, and progress",
    summary: "See the recorded decisions and reverse supported steps without losing the original upload.",
    keywords: "undo history audit review cancel progress automatic run revision changes original recovery",
    items: [
      { title: "Inspect what happened", text: "History records cleaning decisions and counts. The change review includes before/after values, original spreadsheet row numbers, and columns. Counts across steps can include a cell more than once." },
      { title: "Undo a step or automatic run", text: "Undo last action, remove a supported history step, or undo an automatic-cleaning run. DataNeat recalculates later decisions from the preserved working baseline. If a later decision would conflict, the undo is blocked with a reason rather than partially changing the sheet." },
      { title: "Progress and cancellation", text: "Long-running work shows its current stage. Where Cancel is offered, cancellation preserves the last committed working copy; it does not reverse earlier completed decisions. The interface rejects stale edits instead of silently overwriting a newer revision." },
    ],
    related: [{ id: "export", label: "Download a readable report" }],
  },
  {
    id: "recipes-batch", title: "Saved choices, recipes, and batch files",
    summary: "Reuse work on similar data while reviewing compatibility and keeping every file separate.",
    keywords: "save load forget choices recipe json batch multiple files repeat reusable template",
    items: [
      { title: "Saved automatic choices", text: "Save, load, or forget the survey choices in this browser. Check the choices and column exceptions for the new file before starting. Saved choices are preferences, not a copy of the original spreadsheet." },
      { title: "Recipes", text: "Tools → Recipes can save or import supported preparation, rules, text mappings, and whole-column operations. Review the proposed result on the target file first. Statistical mean/median/mode are recalculated for the new file; constants stay fixed. Row-specific edits, ignored findings, models, and record merges are not transferred." },
      { title: "Batch processing", text: "Apply a compatible recipe to several files after previewing each one. Each upload keeps its own result and status. Batch does not append files together, join tables, or combine worksheets; Excel batch processing uses the first worksheet." },
    ],
  },
  {
    id: "export", title: "Review, download, and finish",
    summary: "Download the cleaned data and an explanation you can read without inspecting technical logs.",
    keywords: "export download xlsx excel csv pdf report zip json complete finish remaining issues",
    items: [
      { title: "Review the result", text: "Open Review & export to check completed work and remaining findings. You can return to cleaning or download the current result after deciding what is acceptable. Remaining review suggestions are not proof the file is unusable." },
      { title: "Excel and CSV", text: "Prepare the current table as XLSX or CSV. Text identifiers and leading zeros are preserved where supported. CSV uses UTF-8 with a byte-order mark for spreadsheet compatibility. Formula-like text is escaped rather than executed." },
      { title: "Readable PDF and detailed audit", text: "Prepare a PDF report describing the steps, counts, and relevant estimate/validation details. Tools also offers a detailed change audit and a ZIP package with the report and recipe, with optional changes. The PDF is in English; full Arabic text shaping is not supported." },
      { title: "What the export preserves", text: "The result is a cleaned table, not a full-fidelity Excel workbook. Other worksheets, workbook formatting, charts, macros, merged cells, and executable formulas are not preserved as an original workbook." },
    ],
  },
  {
    id: "account-files", title: "Your account and saved files",
    summary: "Keep selected files and their cleaning history with a verified account instead of letting them expire as temporary uploads.",
    keywords: "my files account google sign in save saved retention temporary storage quota reopen rename delete original history",
    items: [
      { title: "Sign in when accounts are configured", text: "Google sign-in and account saving need authentication setup by the deployment operator. When setup is incomplete, DataNeat explains that account saving is unavailable; local temporary-file cleaning still works. An account is verified by the sign-in provider, not created merely by visiting the page." },
      { title: "Choose which files to keep", text: "In the cleaner, choose Save to my files. This explicitly saves the original upload, current working copy, and cleaning history to your account. Further cleaning changes are saved with that file. Files you have not chosen to save remain temporary and expire after 24 hours." },
      { title: "Return to saved work", text: "Open My files in the sidebar, search by file name, and choose Continue cleaning to reopen the current working copy and history. You can rename the saved entry or permanently delete the file after confirmation." },
      { title: "Retention and account limits", text: "Saved files do not expire automatically and remain until you delete them. My files shows the account's file-count and storage limits; originals and history count toward storage. Make temporary removes a file from My files and starts a new 24-hour expiry period. Account saving is not unlimited storage." },
      { title: "Saved files versus saved choices", text: "My files stores the spreadsheet and its cleaning history on the DataNeat server. Saved automatic choices are only reusable preferences in this browser. In the local deployment, saved account files still live on the host computer; opening them requires DataNeat's services to be running and does not provide a separate online backup." },
    ],
    related: [{ id: "history", label: "Understand cleaning history" }, { id: "privacy-limits", label: "Storage and local access" }],
  },
  {
    id: "privacy-limits", title: "Privacy, file limits, and practical boundaries",
    summary: "Know where the data is processed and what this version can handle.",
    keywords: "privacy security retention 24 hours 20mb 100000 rows 200 columns docker localhost limits server ai storage",
    items: [
      { title: "Files and retention", text: "Default upload limits are 20 MB, 100,000 rows, and 200 columns. CSV and XLSX are supported. One worksheet is cleaned at a time. Temporary uploads expire after 24 hours and are removed during cleanup. Files explicitly saved to a verified account keep their original, current copy, and history without automatic expiry until deleted, within the account limits shown in My files." },
      { title: "Where processing happens", text: "DataNeat processes files on the server running the app. In this local deployment, that is the host computer. It does not send spreadsheet contents to an external AI service. Originals are preserved while the working copy is edited; the deployment operator controls infrastructure access and backups." },
      { title: "Local access", text: "The localhost address works on the same computer while DataNeat's services and Docker are running. It is not a public website address. The URL does not need to change for each local session." },
      { title: "What still needs judgement", text: "DataNeat cannot determine every value's real-world meaning. It does not recover precision already lost in Excel, infer arbitrary date schedules, join files, recursively flatten JSON, or guarantee that a statistical estimate is correct. Review assumptions and preserve values that are valid for your domain." },
    ],
  },
];

export default function GuidePage() {
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    setCollapsed(localStorage.getItem("dataneat-sidebar-collapsed") === "true");
    const savedDark = localStorage.getItem("dataneat-theme") === "dark";
    setDark(savedDark);
    document.documentElement.classList.toggle("dark", savedDark);
  }, []);
  const matches = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return sections.filter(section => {
      const text = [section.title, section.summary, section.keywords, section.note, ...section.items.flatMap(item => [item.title, item.text])].join(" ").toLocaleLowerCase();
      return terms.every(term => text.includes(term));
    });
  }, [query]);
  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("dataneat-theme", next ? "dark" : "light");
  };
  function openSection(id: string) {
    // Related links may point to a section hidden by a search. Reveal it before the anchor jump.
    setQuery("");
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ block: "start" });
      window.history.replaceState(null, "", `#${id}`);
    });
  }
  return <div className={`app-shell guide-shell${collapsed ? " sidebar-collapsed" : ""}`}>
    <WorkspaceSidebar active="guide" collapsed={collapsed} dark={dark} onToggle={() => {
      const next = !collapsed;
      setCollapsed(next);
      localStorage.setItem("dataneat-sidebar-collapsed", String(next));
    }} onTheme={toggleTheme} />
    <div className="main-shell">
      <header className="topbar guide-topbar"><div className="breadcrumb">Workspace <span>Website guide</span></div><a className="button outline" href="/workspace">Open data cleaner <ArrowRight size={15} aria-hidden="true" /></a></header>
      <main className="website-guide" id="guide-top">
        <header className="guide-intro">
          <span className="guide-eyebrow"><BookOpen size={15} aria-hidden="true" /> YOUR DATANEAT HANDBOOK</span>
          <h1>A clearer path to clean data.</h1>
          <p>Learn what each tool does, where to find it, and what to check before applying a change.</p>
          <div className="guide-assurances"><span><ShieldCheck size={15} aria-hidden="true" /> Original preserved</span><span><CheckCircle2 size={15} aria-hidden="true" /> Review before changing</span><span>Manual and automatic, one working copy</span></div>
        </header>
        <div className="guide-search-area">
          <label htmlFor="guide-search">Find an answer</label>
          <div className="guide-search"><Search size={19} aria-hidden="true" /><input id="guide-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Try dates, KNN, empty cells, or Undo" autoComplete="off" aria-controls="guide-sections" />{query && <button type="button" onClick={() => setQuery("")} aria-label="Clear guide search"><X size={17} aria-hidden="true" /></button>}</div>
          <p role="status" aria-live="polite">{query.trim() ? `${matches.length} ${matches.length === 1 ? "section matches" : "sections match"} your search` : "Start with the quick guide or jump to a topic below."}</p>
        </div>
        <div className="guide-layout">
          <nav className="guide-contents" aria-label="Guide topics"><h2>In this guide</h2>{matches.map(section => <a key={section.id} href={`#${section.id}`}>{section.title}</a>)}<a className="guide-privacy-link" href="/privacy">Read the privacy policy <ArrowRight size={13} aria-hidden="true" /></a></nav>
          <div className="guide-sections" id="guide-sections">
            {!matches.length && <section className="guide-no-results"><Search size={24} aria-hidden="true" /><h2>No matching sections</h2><p>Try a shorter term, such as “date”, “missing”, “merge”, or “export”.</p><button type="button" className="button outline" onClick={() => setQuery("")}>Show all topics</button></section>}
            {matches.map((section) => <section className="guide-section" id={section.id} key={section.id} aria-labelledby={`${section.id}-heading`}>
              <header><span className="guide-section-number">{String(sections.indexOf(section) + 1).padStart(2, "0")}</span><div><h2 id={`${section.id}-heading`}>{section.title}</h2><p className="guide-section-summary">{section.summary}</p></div></header>
              <div className="guide-section-items">{section.items.map(item => <div className="guide-feature" key={item.title}><h3>{item.title}</h3><p>{item.text}</p></div>)}</div>
              {section.note && <div className="guide-note"><ShieldCheck size={17} aria-hidden="true" /><p>{section.note}</p></div>}
              {section.related && <div className="guide-related"><span>Related:</span>{section.related.map(link => <a key={link.id} href={`#${link.id}`} onClick={event => { event.preventDefault(); openSection(link.id); }}>{link.label} <ArrowRight size={13} aria-hidden="true" /></a>)}</div>}
            </section>)}
            {matches.length > 0 && <footer className="guide-footer"><p>Your data, your decisions. Use the tools that fit your file and review the assumptions.</p><a href="#guide-top">Back to top ↑</a></footer>}
          </div>
        </div>
      </main>
    </div>
  </div>;
}

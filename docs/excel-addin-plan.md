# DataNeat Excel add-in — proposed plan

Status: **proposal only, not started.** This document defines the scope,
architecture options, phases, risks and the decisions needed from the owner.

## 0. Confirmed decisions (this round)

- **Windows desktop only** for the first release.
- **Excel desktop only** (no Excel on the web initially).
- **Cloud fallback allowed**, but only after explicit per-user consent; local
  mode remains the default.
- **Companion app is acceptable** (signed local DataNeat engine installer).
- **Automatic mode is cleaning only.** Imputation is **not** available in
  automatic mode; it remains a manual/reviewed action.
- **Distribution: private sideload for a few known users.** Signed installer +
  manifest + short install instructions; no AppSource/tenant-wide deployment
  for v1.
- **Highlights: recommended defaults confirmed** — soft tint by issue family,
  thin colored left border, header count, optional cell note, original fills
  stored in a hidden sheet and restored by *Clear highlights*.
- **Data size: Tier XL confirmed** — up to ~10,000,000 cells, e.g. 500k rows ×
  20 columns, workbook up to 100 MB, with the batch-mode conditions in
  section 5. This is not an instant-interaction tier.

## 1. Goal

Use DataNeat inside Excel without leaving the workbook:

- Show issue highlights directly on the worksheet (same issue families and
  counts as the website).
- Review and apply corrections in a DataNeat task pane next to the sheet.
- Run automatic cleaning of the whole sheet from saved/pre-defined settings.
- Preserve the original values and never apply a silent or ambiguous change.
- Keep the data local unless the user explicitly chooses otherwise.

## 2. Architecture options

### Option A — Office.js add-in + existing hosted DataNeat API

The task pane reads the sheet with Office.js, uploads the used range to
`arsany.pythonanywhere.com`, then paints issue highlights from the response.

- Fastest to build; reuses the entire server engine and workflows.
- Requires internet and sending workbook data to the hosted service.
- Conflicts with the “local” and privacy requirements; acceptable only as an
  optional cloud mode.

### Option B — Office.js add-in + local DataNeat engine (recommended)

The Excel task pane talks to a small local companion service that packages the
existing Python cleaning core (FastAPI + pandas + phonenumbers).

- Fully local/offline once installed; no workbook data leaves the machine.
- Reuses the tested profiler, issue detector, cleaning plan, date/percentage
  logic, audit rules instead of reimplementing them in JavaScript.
- Requires installing a signed companion app and trusting a localhost HTTPS
  certificate for the add-in webview.
- Windows first; macOS support adds packaging and trust work.

### Option C — Office.js + WebAssembly engine in the task pane

Bundle a Python runtime (Pyodide) or a TypeScript rewrite inside the add-in.

- No installer, works in Excel on the web theoretically.
- 30–100 MB startup payload, slow first analysis, and a high risk of behavioural
  drift from the Python engine. Not recommended for parity.

**Recommendation:** Option B, with Option A retained as an optional “online
mode” for Excel on the web or machines that cannot install the companion app.

## 3. Components

### 3.1 Excel add-in

- `manifest.xml`: task-pane add-in plus a **DataNeat** ribbon tab with
  `Analyze`, `Clean`, `Highlight`, `Settings`, `Undo`.
- Task pane: React + TypeScript, reusing DataNeat design tokens and components
  (issue chips, review panel, cleaning plan, settings).
- Workbook adapter in Office.js:
  - Read `worksheet.getUsedRange()` values, formulas, text and number formats in
    bounded chunks.
  - Detect headers, hidden rows/columns, merged cells, tables and protected
    sheets.
  - Write corrections only to the affected cells; never rewrite the whole sheet.
- Settings stored in `Office.context.document.settings` (per workbook) with a
  versioned JSON schema, so a saved profile travels with the file.

### 3.2 Local engine service

- Reuse `backend/app` core modules (profile, issues, plans, imputation,
  percentage/date/phone rules).
- FastAPI bound to `127.0.0.1` on an ephemeral port; bearer token generated at
  startup and passed to the task pane.
- Packaged with PyInstaller into a signed Windows installer (Inno Setup);
  optional auto-start; no admin rights if installed per-user.
- HTTPS with a locally generated certificate added to the current user’s trust
  store, because the add-in task pane itself is served over HTTPS.
- A small JSON/SQLite store for settings, recent runs and an undo journal.
- macOS: `.pkg`/`.app` + launchd agent as a later phase; Excel on the web cannot
  run the local helper (cloud mode only).

## 4. Issue highlighting inside Excel

- Analyze the used range and return a compact issue map
  `{row, column, kind, count, examples}`.
- Paint in batches, not cell by cell:
  - soft fill tint per issue family;
  - left or top border accent;
  - short cell note/comment with the issue reason;
  - header cell badge with the total count.
- A **hidden `DataNeat` worksheet** stores:
  - original cell values and fills for the analyzed range;
  - the issue map and settings snapshot;
  - the cleaning log and recipe.
- `Clear highlights` restores the previous fills exactly.
- Unsupported cases (protected sheets, merged cells, formula cells) are flagged
  and skipped rather than modified.

## 5. Cleaning workflow in Excel

1. **Analyze** the active sheet/table/used range.
2. Show the same issue families and counts as the website, with a preview.
3. Choose **Manual review**, **Guided**, or **Automatic**.
4. Automatic uses the saved profile; ambiguous or destructive cases are skipped
   and stay highlighted.
5. Apply only after an explicit preview/confirmation.
6. Write a report + changelog and offer **Undo last run** (snapshot-based;
   Excel’s native undo does not reliably cover add-in edits).
7. Never touch other sheets unless the user selects them.

### Automatic mode — cleaning only (confirmed)

Automatic mode applies deterministic cleaning rules from the saved profile. It
**never invents values** and never imputes.

Allowed in automatic mode (when enabled in the profile):

- trim leading/trailing and repeated whitespace;
- standardize capitalization;
- convert recognized missing-value labels (NA, null, `-`, etc.) to empty cells
  — actual blanks stay empty and are **not filled**;
- normalize boolean labels;
- normalize dates only when the format/interpretation is unambiguous
  (day-first/month-first must be declared for ambiguous dates);
- normalize number/currency/percentage **notation** with a declared scale;
- standardize phone format with a declared region;
- remove exact duplicate rows only if that option is enabled.

Never in automatic mode:

- imputation of missing values;
- guessing ambiguous dates or percentage scales;
- currency conversion or unit conversion without explicit settings;
- changing identifiers, formulas, protected sheets, or unrelated columns;
- destructive structural changes outside the enabled options.

Manual review remains available for every issue, and any value-changing action
is listed in the report and can be undone.

### Pre-defined settings profile

Per column or by overrides:

- declared data type and identifier protection;
- missing markers (`N/A`, `null`, `-`, blanks);
- date order, invalid-date policy and output format;
- percentage scale (points vs ratios);
- currency notation and symbol policy;
- boolean label set and output form;
- phone region and output style;
- capitalization/whitespace policy;
- duplicate-row removal;
- imputation method, group/order and safety acknowledgements;
- automatic vs review-only per issue family.

The profile is versioned, exportable/importable as JSON, and starts in
**safe-only** mode (format normalization, no value invention).

### Data-size tiers (decision 5)

Excel itself allows ~1 million rows, but an add-in is limited by the Office.js
webview, the amount of data moved between Excel and the local engine, and the
time to paint highlights/write corrections. These are the realistic tiers for
Windows desktop with the local companion app:

| Tier | Max cells | Example | Workbook file | Expected analysis | Practical notes |
|---|---|---|---|---|---|
| XL **(selected)** | 8–10,000,000 | 500k rows × 20 cols | up to 100 MB | 2–5 min | batch/file-based mode; 16 GB+ RAM |
| L | 3,000,000 | 100k rows × 30 cols | up to 50 MB | 20–60 s | interactive ceiling |

The tier sets the supported maximum, not the typical file. With XL selected, the
architecture must use file-based ingestion and streaming analysis; L remains the
interactive experience for workbooks within 3M cells.

**Selected: Tier XL — up to ~10,000,000 cells / 100 MB.** This is a batch mode,
not the interactive tier. It requires the following design changes:

- **File-based ingestion:** reading 10M cells through `range.values` is not
  practical. The add-in uses Office.js `getFileAsync(Compressed)` in slices and
  streams the workbook to the local engine, which opens the selected sheet with
  read-only/chunked XLSX parsing. Direct range reads are used only for small
  fallbacks.
- **Streaming analysis:** the existing pandas profiler loads the whole table.
  XL needs chunked profiling/counting so memory stays bounded; this is
  additional engine work, not just a limit change.
- **Highlight cap:** per-cell formatting for millions of flags is not feasible.
  The default is to highlight up to **200,000 affected cells** per run; beyond
  that the task pane shows full per-column totals and the sheet shows header
  badges plus highlighted sample cells. The cap can be raised at the cost of
  time.
- **Batch apply:** automatic cleaning writes only affected cells in chunks with
  progress and cancel. Applying can take **several minutes**; Excel will be
  busy during each write chunk.
- **Hardware:** 64-bit Windows/Office, **16 GB RAM minimum (32 GB for
  text-heavy workbooks)**. XL is not suitable for low-spec machines.
- **Formats:** `.xlsx`/`.xlsm` (macro-enabled workbooks are preserved);
  legacy `.xls` and password-protected workbooks are not supported initially.
- **Fallback option:** if writing millions of changed cells in place proves too
  slow, the companion can export a cleaned workbook and the add-in can offer
  that as the XL completion path; the in-place path remains the target.

Expected XL timings on a typical 8–16 GB laptop: analysis **2–5 minutes**;
highlighting **30–90 seconds** for the capped set; automatic apply **several
minutes**. The output must therefore use explicit progress, cancellation and a
completion report rather than pretending to be instant.

**Recommendation for the first release:** implement the same engine with XL as
the **supported maximum**, but keep Tier L (<3M cells) as the "interactive"
experience. XL users get the batch workflow. Building XL directly is more work
than M/L because of file ingestion and streaming profiling.

## 6. Excel constraints to respect

- Office.js is asynchronous, batched and subject to payload/time limits; plan
  chunks (for example 20–50k cells per sync) instead of one huge range.
- Programmatic changes are not reliably in Excel’s undo stack; DataNeat needs
  its own snapshot/undo.
- Protected sheets, merged cells and shared workbooks may block edits.
- Cell fills are the only practical non-destructive highlight; comments/notes
  are supported but can be noisy, so make them optional.
- A local companion executable cannot be installed by an AppSource add-in
  automatically; company/sideload distribution is required for Option B.
- Cross-platform behavior differs; test Windows desktop, Mac desktop and Excel
  on the web (cloud mode only).

## 7. Delivery phases

| Phase | Scope | Estimate |
|---|---|---|
| 0 | Decisions: platforms, offline requirement, install tolerance, distribution model, size limits | 1–2 days |
| 1 | Office.js task pane + file-based ingestion + streaming analyzer + capped highlights + per-workbook settings | 4–6 weeks |
| 2 | Batch cleaning preview/apply + automatic profile + undo journal + progress/cancel + report | 3–4 weeks |
| 3 | Local engine installer, HTTPS trust, auto-start, Windows signing, memory safeguards | 2–3 weeks |
| 4 | Hardening, XL test matrix, optional cloud fallback with per-user consent | 2–3 weeks |
| 5 | AppSource/enterprise distribution (optional; not required for v1) | 1–3 weeks |

## 8. Acceptance criteria

- The same CSV/XLSX yields the same issue families/counts in Excel and on the
  website for a shared fixture set.
- Highlights appear only on affected cells and are fully removable.
- Automatic cleaning never changes values outside enabled rules; every change
  is listed in the report and can be undone in one action.
- The original sheet values are recoverable from the hidden backup.
- No data leaves the machine in local mode.
- Works with formulas, hidden rows, merged cells (skipped), protected sheets
  (read-only warning), tables and multi-sheet workbooks.
- The task pane stays responsive on the supported maximum workbook size.

## 9. Decisions status

Answered:

1. Platforms: **Windows desktop only**.
2. Local/cloud: **local default; cloud fallback with per-user consent**.
3. Install: **companion app acceptable**.
4. Distribution: **private sideload for a few known users**; signed installer +
   manifest; no AppSource or tenant-wide rollout for v1.
5. Data size: **Tier XL — up to ~10M cells / 100 MB**, with the batch-mode
   conditions in section 5.
6. Highlight style: **recommended defaults** — soft tint by issue family, thin
   colored left border, header count, optional cell note, original fills stored
   and restorable.
7. Automatic safety: **cleaning only; no imputation**.
8. Excel versions: **desktop only** for the first release.

Before implementation starts, confirm the XL operating conditions:

- analysis may take **2–5 minutes**;
- automatic apply may take **several minutes** and Excel will be busy during
  each chunk;
- per-cell highlighting is capped at **200,000 affected cells** per run, with
  column/header summaries beyond that;
- the companion requires **16 GB RAM minimum (32 GB recommended)** and 64-bit
  Windows/Office;
- if in-place writes of millions of cells are too slow, the fallback is a
  companion-generated cleaned workbook.

If those are acceptable, implementation starts with the file-ingestion and
streaming-analysis layer. If you would rather have a snappy in-Excel experience,
choose Tier L instead (up to 3M cells) and XL can be added later as a separate
batch mode.

## 10. Recommendation

Start with **Phase 0 + 1 on Windows desktop**, using **Option B** (local engine),
a **safe-only automatic profile** and **Tier XL as the supported maximum**. XL
requires the file-ingestion/streaming analyzer from the start, so Phase 1 is
larger than an M/L build. The first usable milestone should be read-only
analysis + capped highlights on a real 500k-row workbook; batch cleaning follows
only after that is measured on the target hardware.

# DataNeat — Complete Project Brief for Handoff to Another AI Chat

**Status date: October 29, 2026 — Time zone: Africa/Cairo.**

This file describes the current local version after reviewing the source code, the user's decisions, and the latest tests. Its purpose is to let a new assistant continue the project without repeating earlier discussions. If it conflicts with README.md, HANDOFF.md, or older notes, start with this file and inspect the current code. Do not treat proposed features or old deployment settings as services that are already operational.

## 1. Product Definition

DataNeat is a web application for cleaning and reviewing spreadsheet files. It is intended for users who want to work with inconsistent data through a sheet-like interface without writing code. The user uploads a CSV or XLSX file, understands its issues, chooses corrections, and downloads a cleaned version and a readable report explaining what happened.

The product combines two paths on **the same working copy**: manual interactive cleaning and optional automatic cleaning based on a questionnaire. It does not use an external AI model to clean the data; its engine uses Python, rules, and local analysis. An inferred column type or a suggested correction is a reviewable inference, not proof that a value is incorrect.

The core principles are preserving the original, making decisions explicit, defining the application scope clearly, maintaining an undoable change history, protecting meaning and units, and keeping visual clutter to a minimum.

## 2. Project Location and Actual Status

- The source version being modified is at `C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable`.
- This directory is **not currently a Git checkout**; the absence of `.git` was verified. Do not assume a branch exists or that `git pull` is available, and do not replace the current version with an older copy.
- Local frontend: `http://localhost:3000/`.
- Backend: `http://localhost:8000/`; Swagger: `http://localhost:8000/docs`.
- Compose project: `dataneat`; containers: `dataneat-frontend-1` and `dataneat-backend-1`.
- `/api/health` returns `ok`. Supabase authentication and Google sign-in are now configured and enabled locally. The owner completed a live Google sign-in in Comet. Google remains External/Testing with the owner's account allowed; the owner explicitly chose to defer public Google availability until a public site/domain exists.
- Docker Desktop must be running when using localhost. The URL stays the same on the same computer, but it stops working when the services stop and is not a public address accessible from any device.
- Cloudflare and Render settings exist, along with older files referring to GitHub and a historical frontend deployment. **It has not been verified here that this public deployment works or matches the latest source.** Do not present it to the user as the complete current website without checking it.

## 3. Current User Journey

1. The first page, `/`, is the cover page. It contains the logo, a Begin cleaning button, a theme toggle, and an illustrative sample sheet.
2. Begin cleaning opens `/login`; login does not precede the cover page.
3. If authentication is not configured, the page shows that accounts are unavailable and provides Continue to local workspace. When Supabase is configured, users can sign in, create an account, or reset their password; Google sign-in requires separate activation.
4. Inside `/workspace`, CSV uploads go directly to analysis. XLSX uploads first show an explicit worksheet picker, even for a single-sheet workbook; no worksheet is silently selected.
5. The stages are Upload → Explore → Review → Export. Explore shows the actual working-copy preview and metrics plus cleaning-method choices; Review contains the existing interactive cleaning tools; Export contains the review summary and downloads.
6. The user chooses Clean manually or Clean automatically. The questionnaire is not a mandatory stage after upload.
7. All cleaning, settings, plans, and analysis operate on the current working file and its changes. There is no separate Advanced mode that returns the user to the original uploaded version.
8. Finally, the user reviews the changes and remaining issues, then prepares a CSV, XLSX, or PDF.

The recommended first option is now **Review suggested fixes**: group common corrections across columns, preview them together and apply one reviewed plan. Guided cleaning and Saved choices are available in the toolbar; the existing manual sheet and automatic survey remain available. The sidebar Website guide opens the searchable `/guide` page separately from an active cleaner.

Advanced names may remain in older files, components, and endpoints for compatibility. This does not mean that the current journey includes a separate Advanced interface.

## 4. Import and What Is Preserved

- Supported formats are CSV and XLSX. The default limits are 20 MB, 100,000 rows, and 200 columns. The frontend reads the size limit from the server; deployment configuration may change it.
- CSV import attempts to detect the encoding and delimiter from comma, semicolon, tab, or pipe; rows with inconsistent widths are rejected.
- Blank or duplicate column names are made unique so operations can run safely.
- XLSX processing works on one worksheet. Import preserves text IDs, leading zeros, and some simple number formats such as zero-padding.
- Formulas are read as text and are not executed. The decompressed ZIP contents of an XLSX file are limited to 100 MB.
- Export produces a **cleaned data table**; it does not preserve an entire workbook with its formatting, charts, macros, merged cells, other sheets, or executable formulas.
- Precision lost in Excel before upload cannot be recovered; long identifiers should be stored as text in the source.
- The original is stored separately, and editing takes place on `editor_df` until the file expires or is deleted.

## 5. Important Decision: No Silent Cleaning When Entering the Sheet

**The current behavior supersedes older requests for automatic preprocessing.** The current interface starts through `POST /api/files/{id}/workflow/init` and begins with a copy of the original data, without silently trimming values or converting missing-value markers.

- A genuinely blank cell and an actual null are treated as missing data.
- Text such as NA, N/A, null, none, empty, blank, missing, not available, `-`, and `#N/A` remains text until the user makes a decision for that column.
- The review prompt Should these labels become empty cells? offers Convert labels to empty or Keep as text.
- Conversion or preservation is a recorded, undoable decision that affects how subsequent operations interpret missing values.
- Columns with an unresolved labels decision are left unchanged by automatic cleaning, with an explanation of why they were skipped.
- Preparation tools let the user review outer whitespace trimming, separately choose whether to reduce internal whitespace, and configure marker lists and exceptions for each column.
- Changing a setting alone does not restore previously converted values; use Undo on the step that changed them.

**Developer trap:** The legacy `/editor/start` route and `prepare_original_preview()` function still apply older preparation that includes trimming and marker conversion. Do not substitute them for workflow/init in the new frontend; doing so would restore unwanted behavior.

## 6. Interactive Sheet and Issue Navigation

- A visible **Automatic cleaning** button in the workbook toolbar lets users open the survey after entering manual cleaning, using the same current working copy and revision. Opening or cancelling it preserves manual changes; unresolved missing-label review remains part of the existing entry flow.

- The sheet has continuous scrolling without user-facing pagination buttons. The backend loads small chunks internally; this is an implementation detail, not visible pagination.
- Virtualization uses **48px** row heights, blocks of 25 rows, and a cache capped at 12 blocks. It includes overscan, prefetching, and cancellation of stale requests when the file, revision, or filter changes.
- **Do not change row heights without updating the entire scrolling engine.** Do not let text change a row's height or add animations that move the sheet.
- Column headers are sticky and opaque. They include the column name, a Settings button, and the count of issue flags for that column across the entire file.
- A cell may have multiple issue types. Colors and small markers identify the types; the count does not always represent unique cells.
- Selecting a column shows the issue types present **in that column only**.
- First issue starts navigation. Next Issue moves to a different issue type and skips repetitions of the same type. It stops and becomes disabled at the last type instead of looping indefinitely.
- Fix this issue opens the appropriate correction. Affected rows can be filtered by column and issue type while retaining original row numbers.
- Search covers the entire file, is case-insensitive, and can be restricted to a column. Ctrl/Cmd+F in the cleaning interface opens the application's search.
- Native browser search cannot see rows that have not been rendered because of virtualization. A jump-to-column-name feature is also available.
- Long values are abbreviated in cells and shown in full in review and correction tools.

## 7. Cell Correction Panel

The panel opens through hover, click, or focus on a cell with an issue. It shows the column, row number, issue, and classification, followed by a Before → After example, the correction and its settings, the application scope, and Apply change in a fixed footer.

- The user chooses **what correction to make first, and where to apply it second**.
- There is no additional Preview button inside the tooltip. A dry run automatically calculates the count and example without writing data. Apply is the actual confirmation.
- Replacement scopes include This cell, Same value in column, and Same issue in column. The last option can correct all differing invalid dates in one command, for example, rather than only identical text.
- Normalizers support one cell or eligible cells in the column; JSON expansion is column-scoped; duplicate removal operates on rows.
- An extra-whitespace issue defaults to Trim, rather than starting with Clear cell.
- The unit/currency symbol field for Add symbol starts blank. Do not prefill `$` or any other implicit choice.
- Any error that blocks Apply appears in red, with an icon and the heading Cannot apply this change, directly above the button, with an understandable reason and an accessibility association.
- If there is no actual change, Apply is disabled with the explanation No changes to apply; never leave the button disabled without a reason.
- This value is correct accepts a specific finding, with audit and Undo support. Other issue types do not automatically disappear.
- Manual replacement text, text-unification values, and user-entered constants are accepted in the cells that changed, so they are not automatically highlighted as errors again while the value remains the same. This reflects user acceptance, not independent proof of correctness. Statistical estimates do not receive this exemption.

## 8. Issue Types and Basic Cleaning

The engine supports missing values, missing labels, whitespace, inconsistent capitalization, unexpected numeric/value types, email syntax, inconsistent boolean labels, currencies, percentages, unit symbols, phone numbers, dates, times and durations, duplicate rows, and the new semantic format types.

- Capitalization options appear as Title, UPPER, and lower, matching the expected result rather than displaying every name in lowercase.
- Boolean handling recognizes true/false, yes/no, y/n, and 1/0 and can standardize a column to true/false, Yes/No, or 1/0.
- Supported currencies and percentages are read as numeric values for appropriate calculations. Do not combine different currencies or ambiguous labels, and do not perform foreign-exchange conversion.
- Percentages require an explicit interpretation of numbers without a % sign. Do not silently multiply or divide by 100.
- Currency, percentage, symbol, and phone controls are separate for their specialized options. Phone handling uses country information when needed; validation does not establish that a phone number or email address actually exists.
- Odd-value detection looks for a dominant family of values and then anomalies, such as text in a numeric column or a percentage among currency amounts. It is a finding for review, not grounds for automatic deletion.
- Column rules define intent/type or identifier status, required/unique constraints, allowed values, numeric/date bounds, a wildcard pattern, scale/currency, severity, and whether negative values are allowed.
- Rules raise flags and do not change data. Patterns use wildcards such as `*`, `?`, and `[0-9]`, rather than executing arbitrary regular expressions.
- Negative values are allowed by default. If the user disallows them in a column, they are flagged as errors, and the user can remove the sign from supported numbers or clear/replace the values. Do not assume every Temperature column uses Kelvin.
- IDs and phone numbers are not numeric measurements merely because they look numeric; preserve leading zeros and meaning.

## 9. Dates, Times, and Durations

### Dates

Input interpretation is separate from output format: preserve, day_first, or month_first. Available formats are:

`YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY/MM/DD`, `DD-MM-YYYY`, and `MM-DD-YYYY`.

Include time is available when needed. Impossible dates, or ambiguous dates without an explicit choice, are not guessed. All invalid-date issues can be cleared/replaced in one command. Format provenance is stored for each generated row so day and month are not swapped during reprocessing.

**Important recent fix:** Selecting Day First + DD/MM/YYYY may confirm the meaning of an existing date without changing its text, leaving `changed_cells=0` despite an important decision. `interpreted_dates` was added to preview, apply, and audit. Apply allows these rows to be confirmed, subsequent operations use the confirmed meaning, and Undo restores the ambiguity. Do not disable Apply solely on the basis of textual change counts.

### Duration Versus Time of Day

- Duration includes values such as `PT45M`, `45 min`, `1 day 3 hours`, `1d3h30m15s`, or elapsed HH:MM:SS. It supports compound English expressions and appropriate fractional values, and outputs HH:MM:SS without wrapping hours after 24.
- Clock time is independent. It recognizes AM/PM and 24-hour time and allows 12-hour or 24-hour output. Noon and midnight have the correct meanings. Do not treat an event time as a duration or vice versa.
- There is no comprehensive Arabic-language support for duration unit names; the user prioritized compound English expressions first.

## 10. Imputation and Estimates

Available methods, depending on column type, are Leave unchanged, Constant, Mean, Median, Mode, Forward fill, Backward fill, Linear interpolation, and Date pattern.

- Mean, Median, and Mode each appear only once. Group by is optional inside the settings: without a group, calculations use the column; with a group, they run within each group.
- The legacy aliases `group_mean`, `group_median`, and `group_mode` remain accepted by the backend and recipes and are unified in the frontend through `lib/imputation-methods.ts`. Do not break older files by removing engine support.
- Grouped forward/backward fills still appear as separate methods.
- Column Settings allows up to 5 grouping columns; the compact popup has a simpler group selector.
- Ordered methods require an ordering column and identification of the entity through groups or confirmation that the rows represent one series. Do not rely on arbitrary order or mix entities.
- Observed values are not replaced. Previously estimated values are not used as donors for another estimate. Estimates remain marked with a dotted underline.
- **In the current implementation**, directional fills and interpolation do not extrapolate beyond observed data; edge gaps remain empty, including with forward/backward fill.
- Rows with missing group keys are skipped. An invalid group remains unchanged with a reason, while valid groups can complete. An error is shown if every targeted group fails.
- Calculations support compatible currencies/percentages after their meaning has been resolved and reject mixed currencies or unresolved scales. Currency/percentage interpolation is not offered without appropriate conversion to plain numbers.
- Date median is an estimated chronological midpoint, not the actual event date. The frontend requires acknowledgment; for date-only values, rounding choices are floor, nearest, or ceil, while a timestamp retains its time. It rejects invalid/ambiguous values or an unprepared mix of timezone-aware and timezone-naive values.
- Audit records, counts, and provenance reflect cells that actually changed, especially for cell scope, rather than candidate counts before scope was applied.

### Date Pattern

This detects a regular sequence with a fixed time interval or calendar months/years, including month-end and leap-year cases. It is not AI that infers any arbitrary pattern.

- It requires at least 3 original dates **and** a default original-date coverage of 60% of the rows in the series/group.
- The frontend offers 50/60/75/90/100%. The threshold is proportional, rather than only 3 dates regardless of file size.
- Every original date must fit the pattern; prior estimates do not count as evidence.
- It fills internal gaps only. It supports explicit ordering or current sheet order for this method; it does not assume every next row is the next day.
- An invalid or ambiguous date blocks inference for the group until resolved, with a clear column name and row number.

## 11. Newer Data Families

These converters were integrated into type detection, Settings/cell correction, history/undo, and export. Detecting a type does not mean every possible representation is supported. Ambiguous settings require an explicit source choice.

1. **Localized and scientific numbers:** dot-decimal, comma-decimal, and Arabic separators; Arabic and Persian digits; scientific notation; plain/scientific output.
2. **Fractions:** ASCII mixed fractions and Unicode fractions, with precision from 1 to 18 decimal places, defaulting to 12. A zero denominator is an error.
3. **Measurement units:** Actual conversion between compatible units of length, mass, volume, temperature, and duration. Values without units require an explicit source, and an explicit target is required. Rounding options range from 0 to 12, defaulting to 6; incompatible dimensions and temperatures below absolute zero are rejected. This is not currency FX.
4. **Numeric dates:** Unix seconds/milliseconds/microseconds or Excel 1900/1904, chosen explicitly. Unix outputs UTC; Excel's fictitious serial 60 is rejected. Do not treat an arbitrary large ID as a timestamp.
5. **Time zones:** IANA source/target zones and an explicit source for naive times. Nonexistent DST times are rejected; repeated times require reject/earlier/later. An existing offset remains an important reference and is not replaced by a guess.
6. **JSON and lists:** Strict JSON rejects duplicate keys and nonfinite values. Canonical formatting and optional trimming/deduplication are supported, as is a single-character delimiter with CSV quoting. Expand creates columns for top-level keys/positions while preserving the original and the row count; nested values remain JSON. It prevents collisions, mixed object/list expansion, and exceeding 200 columns, while preserving leading-zero strings and large-number/Decimal precision.
7. **Coordinates:** Latitude/longitude or explicitly ordered pairs, decimal or DMS with a hemisphere, decimal output, and bounds checking at ±90/±180. No geocoding.
8. **URL and IP:** HTTP/HTTPS validation/normalization with an IDNA host and optional https addition; preserves path/query case and rejects invalid credentials, ports, or syntax. IPv4/IPv6 compressed/expanded notation. No browsing, DNS, or proof that a link is reachable.

The product groups these into eight families; the engine has more semantic type names. Action names are `normalize_number_format`, `convert_units`, `convert_numeric_dates`, `convert_timezone`, `normalize_structured`, `expand_structured`, `normalize_coordinates`, `normalize_url`, and `normalize_ip`.

If a new converter encounters an invalid value, it stops **the operation within its scope** with a message identifying the column, row, and value, without partial writes. Cell scope checks only the selected cell. Do not generalize this behavior to every older normalizer; some older converters skip unconvertible values with a warning.

## 12. Automatic Cleaning and Exceptions

The questionnaire is optional. After the user answers it and clicks Start automatic cleaning, the selected policies may be applied across the file without separate confirmation for every cell, with history/undo and an explanation of what did not change.

The current questions are:

- Trim extra whitespace: defaults to true within the questionnaire only, not upon file upload.
- Boolean labels: preserve/true_false/yes_no/one_zero.
- Capitalization: preserve/Title/UPPER/lower.
- Date interpretation: preserve/unambiguous/day_first/month_first.
- Date output: one of the six formats; defaults to YYYY-MM-DD if date standardization is selected.
- Missing numeric measurements: preserve/median/mean.
- Duplicate rows: defaults to preserve, or remove full duplicates with keep first after the other cleaning operations.

Each column-oriented policy has Add exception: the user selects one or more suitable columns and an alternative policy or preserve, and can edit/delete the exception. An exception changes only that question; the other answers are inherited. Duplicate removal is a dataset-level decision without a column exception.

Answers can be saved locally with Use these choices next time, followed by Load/Forget saved choices. The key is `dataneat-automatic-choices-v1`; this is not cloud synchronization.

A run preserves identifiers and skips columns containing accepted manual corrections or unresolved missing labels. Automatic missing-value estimation is limited to fully eligible plain numeric measurement columns; currencies, percentages, units, and date estimation require an appropriate manual choice. The questionnaire **does not automatically run every new converter**. Undo is available for the entire run and for its individual steps.

## 13. Column tools, text unification, and cleaning plans

- Column Settings works on the same current working copy, with Settings, Insights, and Cleaning plan tabs.
- Actions include normalization, imputation, negative-value policy, duplicate subsets, renaming, and the specialized converters described above.
- Users can stage up to 100 actions, select Preview cleaning plan, and then Apply reviewed plan. Preview does not save changes. Application is atomic, and each action becomes a recorded step.
- Renaming carries rules, marker settings, ignored findings, and provenance to the new name and participates in replay. In a draft UI plan, keep rename last until the plan is applied; build subsequent operations against the new name afterward.
- Unify text values lets users select at least two distinct values and enter their exact final representation, for example Cairo/Kairo -> Cairo. It displays frequencies and the affected count before application and preserves missing cells.
- Spelling suggestions are local string-similarity suggestions among the 1,000 most frequent values, each up to 100 characters long. They do not establish semantic or transliteration equivalence. Users choose the sources and final text. The value picker displays up to 300 matching results; narrow the search to reach others.
- Tools contains Preparation, Column rules, Recipes, Batch, Review, Exports, and Recheck issues. Help & legend opens when needed rather than permanently crowding the sheet.

## 14. History, undo, change review, and recipes

- Cleaning history presents numbered expandable steps with action, column, count, scope, and a per-step Undo icon. Undo last action and Undo automatic cleaning run are also available.
- Undo replays surviving decisions from a preserved baseline. It does more than remove a visual history entry. If a later step depends on the removed step, undo fails atomically with an explanation and preserves the data. The dependent step may need to be undone first.
- Complete cell audit for enhanced workflow steps records before/after values, row, column, revision, action, step ID, removed rows, and newly added columns.
- Counts describe changes per operation. The same cell can change multiple times, so their sum is not a count of unique cells across history.
- Some older sessions use a migration baseline with sample-only historical records. Do not claim complete cell audit or undo support for older steps without IDs.
- Review supports text, column, action, and revision filters. Audit review and before/after comparison may paginate at 50 records; that is separate from the continuous spreadsheet view.
- Version 1 JSON recipes transfer reviewed preparation, rules, text mappings, and whole-column operations. They exclude row-specific edits, issue-clearing replacements, and ignored findings. A recipe is not a complete record of every manual action.
- Recipe compatibility checks report missing/extra columns and mapping warnings. Mean, Median, and Mode are recalculated on the destination file; constants stay fixed. Recipes support up to 200 decisions.
- Batch processes files separately, with preview before applying a compatible recipe. One file's failure does not combine or corrupt the others. XLSX batch currently uses the first worksheet; use individual upload to select another sheet. Already uploaded files can recover in the same browser tab; files not yet uploaded must be selected again.

## 15. Exports and readable reports

- The results page has three clear cards: Excel workbook, CSV data, and Cleaning report.
- XLSX and CSV reflect the current working copy. The human-readable English PDF explains recorded cleaning steps instead of requiring ordinary users to interpret JSON.
- Additional tools under Tools also expose a complete JSON change log and a ZIP review package.
- The ZIP contains report.pdf and recipe.json, with changes.json included only when selected. It does not contain the complete original upload.
- PDF examples are nonexhaustive. The enhanced workflow's JSON change log is the more complete record. Full Arabic PDF shaping is not implemented.
- CSV uses UTF-8 with a BOM. Formula-like text and headers are escaped with an apostrophe on export; executable formula preservation is not promised.
- Downloading a PDF alone does not count as backing up the spreadsheet. Download tracking is tied to file and revision. Leaving or resetting may warn if the latest CSV/XLSX has not been downloaded or a task is running.
- Reports, recipes, and audit logs can contain column names and before/after values. Do not place real user data in a general handoff or public examples.

## 16. Approved design and preservation requirements

The approved identity is **Compact**, rather than the earlier Minimal or Studio proposals. Its logo uses three spreadsheet-like cells arranged into a check mark. It is a code-native SVG, not a large mockup image. Main logo colors are `#217346`, `#38a96c`, and `#8dddb1`, with brighter alternatives for dark mode.

- The slim sidebar contains Data cleaner, Privacy policy, personal workspace information, a retention note, theme switching, and collapse controls. Its dark background is `#292c2a`.
- The mark is consistent across the cover, login, sidebar, and small workspace footer.
- The application uses Excel-family green and layered charcoal surfaces: page `#202020`, sheet `#2b2b2b`, and drawer `#343434`.
- The workbook ribbon groups actions into Explore, Clean & review, Guide, and Finish.
- Column headers are opaque and subdued, with a green accent on the selected column. Subtle zebra striping preserves issue highlights.
- Correction panels show Before/After and a fixed Apply footer. Blocking errors are prominent and red.
- History and missing-label cards have internal padding, compact readable text, and wrapping for long column names.
- The cover spreadsheet stays stationary. Only colors and example values fade between Kairo -> Cairo, N/A -> empty, and TRUE -> Yes. These are illustrative choices, not a silent conversion policy. The owner rejected shaking or moving the sheet itself.
- Theme switching is available before login and within the application. It persists through `localStorage:dataneat-theme`. Sidebar collapse state also persists. Respect `prefers-reduced-motion`.

The latest design authorization was specifically to **change the sidebar and logo only**. Implementing Compact was not permission to redesign the spreadsheet or alter cleaning workflows.

## 17. Technology and source map

Frontend: Next.js 16.4.0 App Router, React 19, TypeScript, Tailwind 4 with custom CSS, Lucide, Radix Slot, and optional Supabase JS. The Docker frontend uses Node 22 Alpine. Backend: Python 3.12, FastAPI, Pydantic 2, pandas 2.2.3, openpyxl 3.1.5, phonenumbers, and ReportLab for PDF output. Exact installed versions are recorded in package-lock.json, requirements.lock.txt, and pdf-dependencies.lock.

All paths below are relative to the project root.

| Path | Responsibility |
|---|---|
| `frontend/app/page.tsx` | Cover and its color-fading sample sheet |
| `frontend/app/login/page.tsx`, `frontend/components/account-access.tsx` | Account boundary, sign-in, signup, recovery, and local continuation |
| `frontend/app/workspace/page.tsx` | Upload, workspace recovery, and application shell |
| `frontend/components/interactive-sheet.tsx` | Main sheet, correction controls, issues, history, and results |
| `frontend/lib/use-continuous-sheet.ts` | Virtualization, cache, and scroll navigation |
| `frontend/components/column-settings.tsx` | Current-copy Settings, Insights, and cleaning plans |
| `frontend/components/imputation-controls.tsx`, `frontend/components/date-median-notice.tsx` | Imputation methods, grouping, ordering, and estimate acknowledgement |
| `frontend/lib/imputation-methods.ts` | Deduplicates historical grouped-statistic aliases in menus |
| `frontend/components/automatic-cleaning.tsx` | Survey, exceptions, and saved choices |
| `frontend/components/data-format-controls.tsx` | Settings for newer data-format families |
| `frontend/components/workflow-tools.tsx` | Preparation, rules, recipes, batch, audit, and exports |
| `frontend/components/unify-text-values.tsx`, `frontend/components/sheet-shortcuts.tsx` | Text unification, search, comparison, and shortcuts |
| `frontend/components/workspace-sidebar.tsx`, `frontend/components/dataneat-mark.tsx` | Approved navigation and logo |
| `frontend/lib/workflow.ts`, `frontend/lib/types.ts` | API client, job polling, and data types |
| `backend/app/main.py` | FastAPI routes, sessions, limits, editor, import, and export |
| `backend/app/models/requests.py` | Request and operation validation |
| `backend/app/core/workflow.py` | Revisioned decisions, provenance, audit, replay, recipes, and rules |
| `backend/app/services/workflow_jobs.py` | Workflow initialization, apply, undo, automatic cleaning, plans, and export jobs |
| `backend/app/core/interactive.py` | Cell annotations, proposals, and correction scopes |
| `backend/app/core/profiler.py`, `backend/app/core/type_detector.py`, `backend/app/core/issue_detector.py` | Profiling and detection |
| `backend/app/core/file_parser.py`, `backend/app/core/cleaner.py`, `backend/app/core/validator.py` | Import, transformations, and result validation |
| `backend/app/core/imputation.py`, `backend/app/core/date_sequence.py` | Imputation and regular date sequences |
| `backend/app/core/date_analyzer.py`, `backend/app/core/duration.py`, `backend/app/core/clock_time.py` | Dates, elapsed durations, and time of day |
| `backend/app/core/data_formats.py`, `backend/app/core/semantic_types.py` | Newer format conversion and semantic types |
| `backend/app/core/currency.py`, `backend/app/core/percentage.py`, `backend/app/core/symbols.py`, `backend/app/core/phone.py`, `backend/app/core/negative_values.py` | Specialized parsing and formatting |
| `backend/app/core/automatic_cleaning.py` | Survey policies and protected columns |
| `backend/app/core/pdf_report.py` | Readable PDF report generation |
| `backend/app/services/storage.py`, `backend/app/services/identity.py`, `backend/app/services/limits.py` | Storage, ownership, authentication, and limits |
| `backend/tests/` | Synthetic regression tests |
| `deploy/cloudflare/`, `render.yaml`, `deploy/RENDER.md`, `deploy/AUTHENTICATION.md` | Deployment/authentication configuration; their presence does not prove activation |

CSS import order matters: `globals.css -> workspace-polish.css -> sheet-refresh.css -> interface-refresh.css -> correction-refresh.css -> cover-refresh.css -> brand-mark.css -> compact-sidebar.css`. Historical overrides exist. Inspect the cascade before changing general selectors. A previous text-clipping cause was `.workspace-drawer .panel` overriding internal padding.

Before editing the frontend, read `frontend/AGENTS.md` and the installed Next.js documentation under `node_modules/next/dist/docs/`. Do not rely on assumptions from older framework versions.

## 18. Important API contracts and state

All routes are under `/api`. The frontend uses a same-origin proxy to the backend. Within Docker, the internal backend address is `http://backend:8000`.

- General: `/health`, `/auth/config`, `/auth/session`, `/auth/me`, `/auth/logout`, and authorized `/admin/usage`.
- Files: `/files/upload`, `/files/{id}/workspace`, `/preview`, `/profile`, `/issues`, `/invalid-dates`, and file deletion. The abbreviated routes after workspace share the `/files/{id}` prefix.
- Current workflow: `/files/{id}/workflow/init`, `/settings`, `/jobs`, `/changes`, `/recipe`, `/recipe-check`, and `/suggestions`, sharing the workflow prefix.
- Jobs: `GET /workflow-jobs/{job_id}`, `POST /workflow-jobs/{job_id}/cancel`, and `GET /workflow-jobs/{job_id}/download`.
- Interactive data: `/files/{id}/editor` and its `/search`, `/compare`, `/scope-counts`, `/next-issue`, and `/text-values` children.
- Legacy routes such as file `/clean` and `/preview-cleaning`, `/jobs/*`, and `/editor/start`, `/fix`, `/undo`, and `/download` remain for compatibility. Do not restore a separate Advanced UI simply to use them.

`file_id`, session ownership, and `editor_revision` are fundamental. Writes require an expected revision; stale writes are rejected. Internal row indices refer to the data; displayed spreadsheet rows generally use `index+2` to account for the header.

`changed_cells` alone does not describe every meaningful decision. Rules, ignored findings, and date interpretation confirmations can change without rewriting text. Account for `interpreted_dates` and the relevant decision metadata.

The current workflow `analysis_schema_version=7` refreshes analysis for older sessions without rewriting their data, history, or revision. Legacy non-workflow editor records retain schema5. When changing profile or cache schemas, consider migration instead of reinitializing user files.

## 19. Background jobs, storage, and privacy

- The workflow pool has three threads, at most eight queued/running jobs, and one active workflow job per file/session. An older two-thread pool serves legacy paths.
- Operations run on isolated copies, then commit atomically if the expected revision still matches. Cancellation is cooperative: a current calculation may finish, but uncommitted changes are discarded. After a commit, use Undo.
- Job metadata persists locally. Same-tab refresh can recover job state. A service restart does not resume CPU work mid-calculation; it can recover a committed result or report an explicit retry error.
- `STORAGE_DIR` controls storage. Docker uses the logical volume `dataneat-storage` mounted at `/app/storage`. Server-created snapshots use pickle; workflow job metadata uses JSON. Never accept client-supplied pickle or change storage formats without migration.
- Ownership checks apply to files, jobs, and downloads. Temporary retention is 24 hours from upload/creation, not the latest edit. Explicitly saved account workspaces do not expire automatically. Making a saved file temporary starts a new 24-hour period. Cleanup runs every 60 seconds. Delete removes the file and associated artifacts.
- The global record cap defaults to 1,000 (`MAX_STORED_FILES`); account save admission defaults to 100 files and 1,024 MB, including originals/history (`MAX_ACCOUNT_FILES`, `MAX_ACCOUNT_STORAGE_MB`). Rate limiting is 120 requests per minute per IP. Do not disable safeguards merely to accommodate rapidly repeated tests.
- Processing happens on the server running DataNeat. In the default local setup that is the user's computer; with a hosted backend it would be the hosting server. Processing is not browser-only.
- External AI cleaning, cloud sync, and live collaboration are not implemented. URL/IP/phone/email checks do not prove a service or person exists.
- Supabase authentication is optional. When enabled, verification occurs server-side and limited usage metadata is retained for 90 days for authorized access. Usage counters exclude spreadsheet cell content and passwords. Do not include credentials or real account information in handoffs.
- The current application is not a distributed, multi-instance production architecture. Keep one backend process worker unless job and storage coordination are redesigned.

## 20. Running, updating, and configuring the application

From the project root on Windows:

```powershell
Set-Location -LiteralPath 'C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable'
docker compose -p dataneat up -d --build
```

To rebuild only the frontend while preserving the running backend and stored data:

```powershell
docker compose -p dataneat up -d --build --no-deps frontend
```

To stop services without deleting stored data:

```powershell
docker compose -p dataneat stop
```

Do not use `down -v` or delete the storage volume to update the website. Do not invent a different Compose project name; it can create a separate set of containers and storage rather than update the user's existing application.

`Start DataNeat.vbs` and `Start-DataNeat.ps1` start Docker when necessary, build/start services, verify readiness, and open the site. A mutex prevents duplicate launcher runs. Readiness-only check:

```powershell
powershell -NoProfile -File .\Start-DataNeat.ps1 -CheckOnly
```

Reference configuration is in `.env.example`: `MAX_UPLOAD_MB`, `CORS_ORIGINS`, `COOKIE_SECURE`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `GOOGLE_SIGN_IN_ENABLED`, and `ADMIN_EMAILS`. Native processes need explicit environment configuration and do not automatically read `.env`. `API_INTERNAL_URL` controls the Next.js proxy; `STORAGE_DIR` controls backend storage.

Native development requires Python 3.12+, Node 22+, and dependencies from the lockfiles. Docker is the verified runtime in this environment. Permanent hosting requires a public backend, correct HTTPS/cookie/CORS/storage configuration, and end-to-end validation. Buying a domain alone does not run the Python service.

## 21. Current verification and evidence

- October 26 UI update: the manual-to-automatic toolbar entry passed production build/TypeScript and browser checks at four widths in light/dark. Tests confirmed that opening/cancelling preserves revision/data, an actual automatic run preserves earlier manual changes, whole-run undo preserves the prior manual step, and pending missing-label review still works. No backend behavior changed.

- Latest full backend regression run: **539 passed**, with two existing deprecation warnings, after adding the reviewed cleaning tools and six usability improvements. This does not establish perfect real-world detection accuracy.
- The production frontend build and TypeScript checks passed after the latest Compact logo/sidebar change.
- Browser checks passed for upload, correction, history/undo, search, CSV/XLSX/PDF downloads, interpretation-only date confirmation, optional grouping and deduplicated imputation menus, date patterns, blocking errors, mobile overflow, and theme behavior.
- The last sidebar/logo change was checked through cover/login, persisted theme/collapse, privacy navigation, five viewport widths, cleaning, undo, search, and CSV export. Backend algorithms did not change in that update.
- QA scripts and screenshots are outside the project at `C:\Users\Arsany Arsanious\Documents\Codex\outputs\dataneat-ui-review`. Examples: `review.cjs`, `date-confirmation-review.cjs`, `imputation-menu-review.cjs`, `history-fit-review.cjs`, `marker-card-review.cjs`, and `compact-sidebar-review.cjs`. They may be absent from a source ZIP; do not assume they are repository contents.
- CUA/node_repl failed in this session with a kernel assets path error. Visual testing used Playwright with headless Microsoft Edge through bundled Node. That is a local testing workaround, not a new application dependency.

To test the **current source** using the installed backend image:

```powershell
docker run --rm --mount 'type=bind,source=C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable\backend,target=/app,readonly' -e PYTHONPATH=/app -e STORAGE_DIR=/tmp/dataneat-tests dataneat-backend python -m pytest /app/tests -q -p no:cacheprovider
```

Mount the entire backend source, rather than only tests against an outdated application image. With an installed virtual environment, run pytest from backend after installing the lockfiles. `npm run build` checks the frontend including TypeScript. Existing Playwright tests require running services and a suitable browser.

## 22. Known limitations and unimplemented capabilities

- DataNeat is not embedded Excel. It does not preserve full workbook features or execute formulas/macros.
- KNN and Iterative multivariate numeric imputation, related-column rules, reviewed fuzzy record merges and IQR/MAD outlier review are implemented as optional interactive tools (see section25). There is no general semantic understanding of arbitrary values. Date-pattern completion supports regular patterns verified against all original observations.
- The automatic survey does not automatically handle every newer data format; explicit converters are available through settings.
- Geocoding, exchange-rate conversion, DNS/URL reachability checks, and real-world email/phone existence verification are not implemented.
- Cloud sync, live collaboration, and external connectors are not enabled. Current public deployment of the latest source is unverified.
- Arabic text is preserved in CSV/XLSX, but full Arabic PDF shaping is not implemented. The product interface and reports are currently in English.
- Large files remain subject to RAM/CPU constraints and the 100,000-row by 200-column limits. Initial analysis may take time. Virtualization reduces DOM work, not backend computation.
- Sessions are temporary. Stored working copies and jobs are not a permanent document repository. Accounts are not configured locally despite the login page being present.
- Review legacy paths before using them. Do not treat every statement in older README/HANDOFF sections as current behavior.

## 23. Owner preferences and continuation guidance

- The owner communicates in Egyptian Arabic and prefers short, clear conversational updates. Lead with outcomes and useful links; provide implementation detail when requested. **This handoff brief, including its copy-paste prompt, must be entirely in English.**
- When the owner clearly requests implementation, complete and verify the work. Do not stop at suggestions or repeatedly ask permission for previously authorized work.
- Major visual changes are easier for the owner to assess through images or previews. Text descriptions alone were insufficient. Show alternatives before implementing unless implementation is explicitly requested or a design has already been selected.
- Preserve existing features. Do not restore a separate Advanced mode or replace the continuous sheet with visible pagination.
- Avoid clipped text, character-by-character wrapping, and messages that consume the spreadsheet area. Check frames, padding, min-width, and buttons in dark mode and on mobile.
- Do not invent determinate progress percentages. Use indeterminate stage indicators when real progress measurements are unavailable.
- Free tools and hosting are preferred. Do not create paid services, require a payment card, or change authentication/deployment simply because configuration files exist.
- Distinguish proposed, implemented, and verified behavior. Do not claim a feature works without code and appropriate verification evidence.
- Use synthetic data for testing. Do not alter the user's active dataset or saved history merely to demonstrate a test.

## 24. Copy-paste prompt for a new AI conversation

> I want to continue developing my existing DataNeat project. Read PROJECT_CONTEXT.md / this complete brief, then inspect the attached source before editing. The current application uses Next.js and FastAPI to clean CSV/XLSX data through one unified interactive workflow and an optional automatic-cleaning survey with column exceptions, history/undo, and readable PDF reports. The approved identity is Compact, with a three-cell check-mark logo. Preserve all existing features, original data, revision checks, and audit provenance. Do not restore a separate Advanced mode or silent preprocessing at interactive startup. The local source is C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable, running through Docker Compose project dataneat at localhost:3000. Review the latest verification, limitations, and historical-document warnings. My new request is: [insert your request here].

**Practical handoff note:** This brief transfers project context, not source files, user datasets, or credentials. If the new assistant cannot access the local folder, provide the project source separately, excluding `.env`, storage/uploads, node_modules/builds, and secrets. Reading this brief alone does not give an assistant the ability to change the website; implementation requires source and runtime access.

## 25. Four reviewed cleaning tools — October 26, 2026

**Tools → More cleaning tools** now opens a shared, responsive modal for Related column rules, KNN & Iterative imputation, Similar records and Outlier review. These extend the current interactive copy; they do not add a separate workflow or alter the automatic survey. Detailed behavior and limits are documented in `docs/reviewed-cleaning-tools.md`.

- Related-column rules compare numeric/date/text columns, check arithmetic totals with tolerance, or require values under an exact condition. Draft analysis and saved rules only flag findings. Explicit reviewed actions recalculate arithmetic targets or clear flagged targets. Invalid/ambiguous operands remain unresolved; new conflicts with other saved rules block recalculation. Up to30 named rules; public preview samples up to500 findings while corrections and sheet flags cover all eligible rows.
- Model imputation uses actual pinned scikit-learn KNNImputer and IterativeImputer on plain numeric measurements with explicitly selected helpers. Training excludes prior estimates/user constants. Review shows deterministic held-out MAE versus a training-median baseline and honestly reports unavailable/poorer validation. Maximum2,000 fitting donors,10,000 missing target cells,8 helpers; cells without usable helper evidence remain empty. Explicit acknowledgement, estimate underlines, audit and PDF validation details are retained.
- Similar records uses bounded sorted-neighborhood comparisons across2–5 fields, optional exact blocking, at most20,000 comparisons and100 shown pairs. Scores indicate similarity, not identity probability. Merge requires per-field choices for all conflicts, a retained original row index and reviewed confirmation. Keep both is a fingerprint-bound decision. Complete deletions and edits are audited; date, estimate and accepted-value provenance follow the selected source through merges and Undo.
- Outlier review offers IQR and normalized MAD bounds, adjustable sensitivity and optional grouping with at least5 observed measurements. Save a check to flag the sheet, then separately review keeping, clearing or capping one/all findings. Missing group keys/insufficient observations/zero MAD are explained. No finding is automatically treated as wrong.
- Integration adds `Decision.kind="quality"` and a read-only `quality_review` background operation; all writes retain revision checks, ownership, cancellation and replay Undo. These reviewed decisions are excluded from transferable recipes. Analysis cache schema is6; existing saved values/history are preserved during upgrade.
- Scope remains the first four proposals only. General split/merge/calculated columns, combined files/sheets, business calendars and deep JSON/range expansion remain unimplemented.

## 26. Six usability improvements and website guide — October 26, 2026

See `docs/easier-cleaning.md` for the full operating contract.

1. **One combined review:** `/workflow/suggested` groups eligible whitespace, boolean, date, time, duration, capitalization and optional exact-duplicate operations. Quick cleaning selects issue groups, format choices and column exclusions, previews a single plan, then applies it once. Only whitespace is initially selected. Original/current-copy, revision, cancellation and audit protections remain.
2. **One decision per issue type:** grouped choices cover suitable columns. Explicit replacements can also target the same annotated issue in selected columns through the new `issue_columns` scope. Only matching flagged cells change; identifier guards and exact per-cell audit/Undo remain. No missing estimates or invalid-value clearing are guessed.
3. **Guided cleaning:** whole-file column/type queue with Fix, Skip and Next, partial-fix count refresh, automatic advancement of resolved types, same-tab progress recovery and truthful reviewed/skipped/remaining completion. Skipping does not accept or erase flags.
4. **Fewer initial controls:** the suggested cell action is prominent; detailed and alternative actions are under More options. Optional replacement scopes are under More scope options. Required settings and blocking errors stay visible. Existing functions remain accessible.
5. **Reusable choices:** named, sanitized notation choices in browser storage `dataneat-cleaning-choices-v1`, at most20 sets/100 actions, with update/delete and fresh compatibility/preview requirements. Cell contents, row references, replacements, estimates, input-date-order judgments and destructive choices are excluded. IDs, accepted-manual columns and unresolved markers are protected on reuse.
6. **Clear ending:** completed selections show their recorded changes; final Review & export distinguishes no detected flags from remaining review flags and keeps download available. Remaining flags are never silently called fixed.

The new public `/guide` page contains15 searchable, anchored sections about workflows, every current tool, examples, exports, privacy, retention and limits. Its sidebar Website guide link opens a new tab from an active cleaner. Existing theme/collapse behavior is reused.

The final production build/TypeScript passed, both services were redeployed locally, and the current-source backend suite passed539 tests. Browser QA passed combined preview/apply and invalidation, multi-column issue replacement, saved settings reuse on a second file, guided Fix/Skip/completion, default/More options visibility, honest finish labels, three viewport widths and light/dark. Guide search, anchors, public access and new-tab navigation preserving the active file were independently verified. Evidence is under `Documents/Codex/outputs/dataneat-ui-review`: `simplified-cleaning-review.cjs`, `simplified-*.png`, `guide-review.cjs`, and `guide-*.png`.

## 27. Resolve other issues before imputation — October 27, 2026

Every newly requested missing-value fill requires the selected column to have no remaining non-missing flags. This includes formatting/review flags, invalid values, unresolved marker labels, declared rules, outliers, cross-column checks and duplicate rows. Correct, clear, or explicitly accept these findings first. A required-value rule on an actually empty cell is allowed; literal NA/null text is not automatically empty.

The server publishes `imputation_readiness` with blocker labels, counts and example spreadsheet rows in each workflow column profile. Interactive correction and column settings show red explanations and disable estimates; the model tool blocks KNN/Iterative review/apply. A constant replacement into an actual empty cell enforces the same rule. Correcting or clearing nonempty values remains available, as does leaving missing values unchanged.

The gate also covers sequential plans/recipes, automatic cleaning and legacy cleaning APIs. Approved earlier cleanup is rechecked before any fill. Automatic cleaning skips blocked fills with a reason while retaining successful cleanup. New imputation/manual-fill steps record `imputation_readiness_policy=1`; removing an earlier cleanup cannot invalidate a later dependent fill silently. Historical unmarked steps remain replayable to preserve existing user work. Pure statistical kernels remain separately testable.

Implementation: `core/imputation_readiness.py`, workflow/profile and quality-model wrappers, workflow jobs, legacy API wrapper, `lib/imputation-readiness.ts`, and correction/settings/model controls. Workflow analysis schema is now7; migration refreshes findings without changing data or history.

## 28. Account file library — October 27, 2026

The application implements optional **Save to my files** and `/files` (My files). Saving keeps the original, current table, settings and full cleaning history together; later confirmed changes are saved automatically. The account library supports search, rename, continue cleaning and confirmed permanent deletion. A temporary file expires after24 hours; a saved file has no automatic expiry. Making a saved file temporary requires confirmation and starts a fresh24-hour window. Opening a new spreadsheet preserves saved files, and saved changes do not trigger the download-before-leaving warning.

Server ownership is the verified Supabase user ID and a stable derived account session, so the same account can resume from a different browser. Another account cannot list/open/edit/download/delete that workspace. Sign-out/account changes clear the tab's private workspace cache and remount account content. The login return path is restricted to local workspace/file-library destinations.

Retention metadata is stored atomically beside the server snapshot. It is independent of cleaning-job snapshots so a late job cannot revert Save, Rename or Make temporary. Purging protects saved files even after service restart or recovery of missing metadata. Job/output artifacts still have temporary retention. The persistent Docker volume must survive host deployments; files are stored on the DataNeat server, not Google Drive or Supabase Storage.

Admission limits default to 100 saved files/1,024 MB per account and 1,000 total stored records. The library shows storage usage; existing saved work remains editable if later history grows above the admission limit. Anonymous local files are not silently claimed when authentication is first enabled.

**Current activation:** the free Supabase DataNeat project is healthy at `https://vdhznrecrwwegdomshva.supabase.co`; local callback `http://localhost:3000/login**` is allowlisted. Google Cloud project ID is `dataneat`, with the approved Web application client named DataNeat Web. Its authorized origin is `http://localhost:3000` and redirect is the project's Supabase `/auth/v1/callback`. Google is enabled in Supabase and the local `.env`. The owner approved the Google policy and creation/configuration of OAuth credentials, then completed the personal Google sign-in. No authentication bypass or fake identity is shipped.

The owner explicitly chose **local testing only for now** because no public site/domain exists. Google is External/Testing with the owner's account in its test audience. The Publish app control requires completing public home/privacy branding. Do not invent URLs, claim public availability, create duplicate projects, or silently add other test accounts. Future public setup must use the real hosted application/privacy pages and verified ownership; see the official links in `docs/google-account-setup.md`.

Live verified-account UI QA on October 28: uploaded a synthetic three-row file, trimmed City whitespace, saved to My files with no automatic expiry, started a new spreadsheet (saved file preserved without a download warning), renamed the entry to Account save test, and reopened it. The renamed working copy retained its corrected data and Trim Whitespace history; Before & after still showed original `" Cairo "` versus current `"Cairo"`. The example remains in the owner's My files. Automated suite: 618 passed. Final frontend/TypeScript builds and both local services passed. See VALIDATION.md for evidence.

The owner requested a written backup of the OAuth credentials. A private local text file exists under `Documents/Codex/private/DataNeat-account-keys.txt`, restricted to the current Windows user. The Google secret is configured in Supabase; only the public Supabase key is used by DataNeat. Do not copy secret values into this brief, source files, screenshots or general handoff documents.

## 29. Approved light dashboard and worksheet selection — October 29, 2026

The approved dashboard has a dark charcoal workspace sidebar in both themes, an off-white light-mode canvas (`#F9F9F8`), white rounded cards, dark text, and Excel-green active controls (`#217346`). Dark mode retains its charcoal surfaces and remains available from the cover/login as well as the workspace. The existing logo, account entry sequence, cleaning tools, history and saved-file behavior remain intact.

The four visible stages are **Upload / Explore / Review / Export**. The active stage is a solid green card with white text. Before upload, there is one dashed drop zone with a decorative empty-grid/upload icon; it has no invented data scores or charts. Explore shows a small actual working-copy preview and real row/column/missing/review-cell counts after analysis. Before & after is disabled until an actual recorded data change exists. The existing cleaning and export handlers still operate on the same working copy.

Typography uses locally bundled Manrope (`frontend/app/fonts/Manrope-Variable.ttf`, OFL license included), with no external font request. Shared readability styles raise ordinary body text to 17px, controls to 16px, labels/actions to 15px and detailed help to 14px. Continuous cleaning-sheet rows retain their fixed **48px** geometry. `dashboard-refresh.css` is imported before the final `readability.css` layer.

Explore's metrics now use equal-width cards below the full-width preview rather than a narrow right-hand panel. Container width chooses four, two or one columns; labels and numbers stay on one line at their existing font sizes. A 32px gap separates the preview/metrics card from the following cleaning-method heading. This is a presentation-only change; counts and cleaning behavior are unchanged.

The owner selected **one worksheet per workspace with clear limits**, rather than simultaneous multi-sheet editing. XLSX selection now calls authenticated `POST /api/files/inspect-workbook` before any analysis. It lists every tab, reported row/column bounds, hidden status and reasons a tab cannot be selected. No sheet is preselected. Empty/header-only, oversized, unsupported and missing-dimension tabs are disabled; valid hidden tabs can be explicitly selected. Limits remain 20MB uploaded, 100MB expanded XLSX ZIP, 100,000 data rows, 200 columns and at most 1,000 tabs. Inspection creates no stored record and does no profiling.

Only the chosen sheet is analyzed, cleaned and exported as a data table. The original workbook remains preserved separately; other sheets, workbook formatting/charts and executable formulas are not carried into the exported cleaned table. The picker, file banner and website guide explain this. Choosing another sheet uses the existing unsaved-change/busy guard. Saved workspaces are preserved; old temporary cleanup is best effort and cannot prevent a successful replacement from opening. A restored workspace without its browser File object asks the user to upload the original workbook to choose another sheet.

Verification: 637 backend tests passed, including 19 multi-sheet/inspection tests. Production frontend build and TypeScript passed. Isolated browser QA covered real three-sheet selection, leading-zero IDs, formula text, guarded switching, cancel/reload behavior, empty/header-only tabs, valid hidden sheets, light/dark/mobile display and existing correction/history controls. Browser test workspaces used separate local containers and synthetic files, not the owner's saved data or an authentication bypass in the shipped app.

The owner asked how to share before deployment. `docs/temporary-friend-sharing.md` explains a temporary Cloudflare Quick Tunnel, exact temporary-origin CORS and Supabase login redirects, and adding a friend's email to Google's Testing audience. **No sharing tunnel was started, no public link was created, and no Google/Supabase sharing settings were changed.** The working local URL remains `http://localhost:3000/`; a temporary share requires the PC, Docker and tunnel to keep running.

## 30. Sidebar account actions — October 29, 2026

The top account bar (Google email, duplicate My files and Sign out buttons) has been removed. Signed-in workspace/files pages expose **Logout** at the bottom of the existing dark sidebar. My files remains in the sidebar navigation. The same existing server/Supabase logout and browser-workspace cleanup run from the new location. Collapsed navigation retains an accessible icon, and mobile keeps the action visible. Public cover/guide/privacy pages retain their existing unauthenticated/public behavior.

Admin Usage overview remains available as a sidebar action only for authorized admins. Its existing table now opens in a native modal dialog so its Close control is not covered by the fixed sidebar. The frontend uses account navigation context to expose these actions; no authentication rules, account-storage behavior, credentials or backend endpoints were changed. Presentation lives in `sidebar-account.css`, imported after `readability.css`.

The owner also requested a multi-sheet synthetic testing workbook. It is saved outside the repository at `Documents/Codex/outputs/01a136e4-87a0-7480-af1f-19dacaf13404/DataNeat-Multi-Sheet-Test.xlsx`. Customers (120), Sales (120), Events (96), DatePatterns (80) and Measurements (96) contain 512 invented records with deliberate cleaning cases; Guide has 23 test instructions. All six tabs are selectable in the real inspector, and the parser reads the expected counts. It was not uploaded to the owner's account. See VALIDATION.md for verification details.

## 31. Column data types, original colors and formula results — October 30, 2026

Column settings now starts with **Column data type**, available from the three-dot button in each column heading. The shared selector also appears under Tools > Column rules. Choices are Auto, Text, Category, Number, Salary / numeric amount, Serial / identifier, Phone, Email, Boolean, Date, Date and time, Clock time, Duration, Location / place name, Geographical coordinate, Currency, Percentage, URL and IP address.

Saving uses an existing versioned rules decision, merges existing rules, refreshes findings and records an undoable history step. Selecting a type does not convert or rewrite values. Explicit choices override name/content inference; Auto restores it. Text no longer receives phone/email checks based only on its heading, and declared nonnumeric columns do not receive numeric imputation recommendations based on names such as Salary. Clock/duration and other typed findings use the chosen type. Serial / identifier retains existing conversion safeguards and leading zeros. Salary maps to an ordinary numeric measurement, not a guessed currency; Location maps to category labels, not coordinates. The same decision survives rename, recipes and account workspace persistence. Workflow analysis schema is now 8; historical references to schema 7 above describe earlier releases.

XLSX original solid background fills are hidden by default. **Show original colors** is available in Explore and Review and is view-only: it does not create a cleaning/history/revision change. Source fills use readable black/white text, while issue edges and warning icons retain cleaning findings. Theme, indexed and RGB fills are supported; original row/column identity is retained through paging, filtering, renames and row removal. New/unmapped columns have no source fill. Conditional formatting, gradients, patterns, fonts, merged-cell display and source header colors are not reproduced. Cleaned exports remain data tables; the original workbook remains preserved. Fill extraction is lazy and bounded/cached, with an explicit unavailable state.

New XLSX imports now read the workbook's saved evaluated formula results instead of formula expressions. Formulas/macros/external links are never executed. Cached zero, false, text, dates and explicit empty string results retain their values. A selected sheet with formula cells lacking cached results is rejected with cell references and instructions to recalculate/save in Excel and re-upload. Excel error results remain visible values for review. The file banner explains that imported formula results are the last saved snapshot and do not recalculate when input data is edited in DataNeat. Existing saved workspaces are not silently re-imported or overwritten; re-upload an original workbook to use the new import behavior.

Validation: 678 backend tests passed on the integrated changes; 45 focused tests passed after final coordinate and source-fill refinements, including four added cases. Frontend production build/TypeScript passed. Isolated real-browser QA used an invented 80-row XLSX, checked cached results, opt-in fills, scrolling alignment, unchanged values/revisions for display, explicit type overrides, 48px rows and light/dark/mobile layouts. No owner account data or Google settings were changed.

## 32. Capacity, read-only review links and optional assistant — November 23, 2026

- Public caps: 5 MiB, 15,000 rows, 75 columns, a 250,000-cell analysis budget, a 300 MB snapshot budget, 200 stored records and 30 saved files / 40 MiB per account. `MAX_UPLOAD_ROWS`, `MAX_UPLOAD_COLUMNS`, `MAX_WORKFLOW_CELLS` and `MAX_STORAGE_MB` are documented in `.env.example`; the local Docker defaults remain 20 MiB / 100,000 / 200 with budgets disabled. The caps were chosen from a measured upload/analysis curve (25k rows ≈ 27s upload + 37s analysis on the development machine).
- `POST /api/files/{id}/share` creates an expiring HMAC token; `DELETE` rotates the per-file share epoch and revokes every issued link; `GET /api/share/{token}` and `/api/share/{token}/report` are the only public API paths. The frontend creates links from Export and serves `/share?t=...` as a static page. Details: `docs/sharing-and-assist.md`.
- `POST /api/assist` is optional, suggest-only and switchable with `AI_ASSIST_ENABLED`. The server extracts bounded samples itself, accepts only fixed OpenAI-compatible provider presets (no arbitrary URLs), never stores or echoes the key, and applies suggestions only through the reviewed, undoable rules decision.
- The Column data type selector now exposes all 18 engine types (Category, Salary, Email, URL, IP, Location and the rest), matching the backend vocabulary.
- Privacy page updated: no third-party AI request unless the user opts in per request; share links are bearer secrets with expiry and revocation.
- The live PythonAnywhere deployment was refreshed with the verified backend files and static export. Replaced backend files were backed up first. Assistant calls additionally require the provider hosts to be whitelisted in the PythonAnywhere account settings.
- Schema note: `ANALYSIS_SCHEMA_VERSION` is 9; earlier sections that say 8 describe previous releases.

## 33. Manual-first cleaning entry — November 23, 2026

- Explore shows a single manual-review card ("Open the spreadsheet"); there is no cleaning-method choice before the sheet.
- "Review suggested fixes" was removed from the Explore card, the workbook toolbar, and the guided-walkthrough completion. The quick-clean endpoint and component were left in the codebase but have no standalone entry point.
- Guided cleaning and Automatic cleaning are available in the workbook toolbar immediately when the sheet opens; the Tools drawer survey is equally available. No prior manual change is required. (A gated version was tested and deliberately removed the same day.)
- The website guide copy for quick start, faster cleaning and automatic cleaning was updated to this flow. Saved choices still opens its existing modal; its internal Suggested-fixes tab is used to build reusable choices.
- Live static export redeployed and audited: 19 referenced workspace chunks return 200, the removed label is absent, and no stale gating copy remains. A headless-browser flow check passed against the same build.

## 34. Automatic-cleaning survey restyle — November 23, 2026

- Survey questions are numbered 1–6 (the sixth is duplicate-row handling) with round green badges. Question labels use the product green; the selected answer inside each select uses the normal text color, so question and answer are visually distinct.
- Spacing between questions increased to 30px (24px below 480px). Styling lives in `frontend/app/auto-cleaning-survey.css`, imported last in `app/layout.tsx`.
- Presentation-only: question order, choices, exceptions, saved choices, auto-cleaning policies and backend behavior are unchanged. Light and dark both checked in a headless browser (`ui-automatic-light.png`, `ui-automatic-dark.png`).

## 35. Date interpretation resolves ambiguous values — November 23, 2026

- In both automatic and manual cleaning, choosing Day first or Month first now rewrites ambiguous dates in the selected output format (05/10/2025 → 2025-10-05 day-first with YYYY-MM-DD). No pattern is ever guessed; "Keep ambiguous dates" still preserves them.
- Automatic cleaning applies the date question to columns declared by the user as Date / Date and time as well as auto-detected date columns.
- Manual cleaning adds explicit quick corrections "Resolve ambiguous dates as day first/month first" and a note when ambiguous values are being kept. Column settings labels describe the same resolution behavior.
- The automatic survey example now selects an ambiguous sample and shows the resolved value, and the guide's date section explains the rewrite.
- Verification: seven new backend tests; full suite 721 passed; TypeScript and static build passed. Deployed backend and static export, verified live.

## 36. Missing-value findings visible again — November 23, 2026

- The sheet previously hid missing-value flags in three places: cell rendering, the issue drawer and the column issue navigation. Column headers still counted them, so a column could display "2 issues" and still report "No issues detected in this column."
- N/A/null/"-" labels now render as flagged cells, appear in the issue drawer and column navigation, and open the Convert labels to empty / Keep as text decision. Empty cells remain visually unmarked but are listed in the navigation and route to Imputation.
- This is presentation/routing only; issue detection and corrections are unchanged. Verified in a headless browser and deployed as a static export.

## 37. Percentage scale foundation (Phase A) and type cleanup — November 24, 2026

- A percentage column with bare numbers and no declared scale now raises a `percentage_scale` review issue. The scale is stored in the existing column-rules field `percentage_scale` (`""` = not declared, `points`, `ratio`). Declaring it never rewrites cells; Normalize Percentage remains the explicit text-changing step.
- Settings UI: the Column data type card shows "Bare numbers without %" for percentage columns, including auto-detected ones. The issue panel and Insights explain that 0.96 could mean 96% or 0.96% and link to that control.
- Gates: mean/median on bare percentage values requires a declared scale (ratio multiplies bare values by 100 for the calculation; points leaves them as written); marked `%` values always use points; mixed marked/bare notation still requires normalization first. Imputation readiness, column-rule bounds, cross-column arithmetic and automatic cleaning all refuse undeclared percentage scales with explicit reasons.
- Analysis schema is now 10. Existing files are re-profiled without changing data, history or revision.
- The redundant Salary type is retired from the picker, column rules and AI suggestions. Backend `salary` remains accepted only for backward compatibility with old rules, recipes and API clients; it renders as Number and new saves use `numeric`.
- Verification: full backend suite 729 passed; TypeScript and static build passed; browser check 3 flags → 0 after declaring ratio. See `docs/percentage-scale.md`.
- Phase B remains: the dedicated dual-preview scale dialog, guided-copy polish and an optional automatic-cleaning survey question.

## 38. Full premium interface redesign — November 24, 2026

- The owner authorized a full visual redesign across every workspace, page and modal. This supersedes the earlier "sidebar and logo only" design authorization; workflow behavior, markup contracts and data handling remain unchanged.
- Design system: `frontend/app/premium-theme.css` (last import) with dark-first tokens: `#0B0F19` base, `#111827` surface, `#1F2937` panels, `#F9FAFB` headings, `#D1D5DB` body, `#9CA3AF` muted, `#374151` borders, `#10B981`/`#34D399` accents. Light mode uses the matching slate/mint counterpart.
- Typography: self-hosted Inter Variable (`frontend/app/fonts/InterVariable.woff2`, OFL) replaces Manrope; monospace fallbacks for data. No external font request.
- Dark is the default for visitors without a saved theme; `dataneat-theme` is still respected and light mode is fully styled. The sidebar is dark in both themes, with a mint logo, 3px active indicator and muted items.
- Restyled all major surfaces: cover, login, upload/Explore, spreadsheet grid, toolbars, issue pills, correction panel, automatic-cleaning survey, column settings, quality tools, My files, guide, privacy and share links.
- The spreadsheet keeps its fixed 48px rows, virtualization and issue semantics; the correction panel is offset from the sidebar on desktop. No API, history, audit, export or storage behavior changed.
- Verification: production build/TypeScript, headless-browser review of all major screens in dark/light/mobile with no page errors, and live deployment checks for the dark default, Inter font and mint primary actions. Details in `docs/premium-ui.md`.

## 39. Upload reliability — November 24, 2026

- Hosted uploads failed with “Server returned an invalid response”. The PythonAnywhere access log proved a **60-second proxy timeout** (`504 response-time=60.039`), not a JSON/API defect: the upload endpoint performed parsing, full profiling, plan generation and the cloud snapshot save inside one request.
- Host profiling benchmark: 50k cells 15.2s, 150k 48.9s, 240k >60s. With parsing/save overhead, the 250k-cell public budget could not fit one request.
- New contract: uploads ≤ `ANALYSIS_SYNC_CELLS` (40,000 cells) stay synchronous; larger uploads save the parsed snapshot, return `analysis_pending: true`, and profile/plan in a FastAPI background task. `GET /api/files/{id}/analysis` returns 202 pending or 200 ready and is retry-safe across worker restarts. The frontend shows “Preparing your data summary…” and polls; restore after reload handles pending records too.
- Also fixed Starlette 1.x's 1 MiB multipart part limit (files 1–5 MiB previously got HTTP 400) by widening `Request.form()` to the configured upload budget. Upload errors now include the HTTP status, and unexpected API exceptions return JSON.
- Verification: 732 backend tests pass (new async/multipart tests included); local 240k-cell upload completed async in ~35s with no page errors and small files stayed instant; the host executes background tasks after the response; backend and static deployment verified live.
- Keep operational note: the host's hard request ceiling is 60s; any future synchronous analysis work must stay well below it. Details in `docs/upload-reliability.md`.

## 40. Correction relevance and upload latency — November 24, 2026

- Cell correction UI is now issue-driven. The fix menu is built from the selected cell's issue kinds plus the column's detected type; irrelevant formatters (units, timezones, dates, URLs, IPs, etc.) no longer appear for a phone flag. Quick suggestions use the same mapping and phone/currency/symbol/percentage now have dedicated quick actions. See `docs/issue-corrections.md`.
- Upload latency: access-log evidence showed ~8.8s per upload and ~65s analysis wait. Upload now always returns on the local snapshot before profiling; the background analysis performs the durable cloud snapshot commit. Polling starts at 500ms for the first 8 seconds, then 1.5s. The hosted app sets `ANALYSIS_SYNC_CELLS=0`, so no upload request performs profiling.
- Remaining limitation: hosted analysis is CPU-bound on the free single worker; very large sheets still take tens of seconds to become ready, but the upload itself returns quickly and the UI shows an explicit “Preparing your data summary…” state. Further speedup would require deeper profiler optimization or a bigger host.
- Excel add-in: proposal only in `docs/excel-addin-plan.md`; no implementation has started. It covers Office.js task pane + local Python helper (recommended), hosted-cloud alternative, highlighting, automatic cleaning settings, packaging, phases and the decisions needed from the owner.

## 41. Excel add-in decisions — November 24, 2026

- Confirmed by the owner: **Windows desktop Excel only** for v1; **Excel desktop only**; **local companion app acceptable**; **cloud fallback permitted only with per-user consent**; **automatic mode is cleaning only and must not include imputation**.
- Automatic mode therefore applies deterministic notation/label cleaning, never invents values, and leaves missing values empty. Imputation stays a manual/reviewed action.
- Distribution confirmed: **private sideload for a few known users** (signed companion installer + manifest; no AppSource for v1). Highlight style confirmed: **soft tint + left border + header count + optional notes, original fills restorable**.
- Data tier confirmed: **XL — up to ~10M cells / 500k rows × 20 cols / 100 MB**, as a batch/file-based mode, not an instant experience. Requires file-based ingestion, streaming analysis, capped per-cell highlighting (200k cells/run), 16 GB+ RAM, and batch apply with progress/cancel. No add-in code has been written yet; implementation awaits final acceptance of the XL operating conditions.

## 42. GitHub repository — November 24, 2026

- The project is now a git working copy of `https://github.com/arsanyarsanious/DataNeat` on `main`. Machine access uses the existing Windows credential manager entry; no token or secret is stored in the repository.
- The portable workspace was merged into the established GitHub history, preserving the 30 existing `main` commits alongside the premium UI, upload reliability, issue-specific correction menus, share/AI work and documentation. The merge commit is `8469f72`; the follow-up UTF-8 repair is `ea143a4`.
- A corrupted-currency-symbol import from an upstream commit was repaired (`€`, `£`, dashes) before pushing.
- Workflow and pre-push test/build commands are documented in `docs/git-workflow.md`. Future changes should be committed and pushed from the project root; `.env`, build outputs, dependencies and logs are ignored.

## 43. Excel add-in Tier L preview — November 24, 2026

- Phase 1 preview is implemented under `excel-addin/`: a Windows local companion serves the existing engine over HTTPS and the Office.js task pane at `https://localhost:9443/taskpane.html`; a validated sideload manifest is included.
- The task pane reads the active sheet, enforces the Tier L ~3M-cell limit, sends the displayed text as CSV to `/api/addin/analyze`, and shows rows/columns/issue cells plus per-column findings. It highlights up to 10,000 flagged cells and stores previous fills for restore (best effort).
- The local companion uses the same profiler/annotator as the website; no data leaves the machine. Setup/run/certificate scripts are in `excel-addin/companion/`.
- Verified in real Excel 365 desktop: task pane loads, analysis runs and returns 17 flagged cells for the test sheet. Highlight writes were refused by this machine's **unlicensed Excel** (Office.js AccessDenied); COM writes work, so the block is the Office license/Protected View, not the analyzer. On licensed Excel, retry after **Enable Editing**. The preview reports a clear write-blocked message.
- Backend: `/api/addin/analyze` plus `backend/tests/test_addin.py`; full suite **735 passed**. Manifest validates with `office-addin-manifest`.
- Remaining Phase 1 work: verify formatting on a licensed Excel, tuning for 1–3M cells, then corrections/automatic cleaning (Phase 2).
- Added an Excel-on-the-web test path: `companion/web-tunnel.ps1` opens a temporary Cloudflare quick tunnel and generates `generated/manifest.web.xml`; the companion allows `*.trycloudflare.com` origins for that test. Web mode uses 1M cells / 5k highlight cap. Browser/tunnel analysis verified; actual Excel-web host test still needs a Microsoft account.

## 44. Canonical agent handoff — November 24, 2026

- `AGENT_BRIEF.md` is the complete current handoff: product, every feature, architecture, API map, tooling, security findings, deployment drift, unresolved backlog and exact start commands. Read it before continuing.
- Key live/current caveat: GitHub `main` (`48f8020`) is ahead of the deployed PythonAnywhere build; the Excel add-in Tier L preview exists only as a local companion/manifest and is not deployed.
- P0 cleanup: remove temporary `/api/diagnostics/*` endpoints + disk fields and rotate `DIAG_TOKEN`; reconcile and verify the live deployment; validate Excel highlighting on a licensed Excel.
- Excel web: the task pane loads and reaches the local engine. Office web's multipart upload caused “There was an error parsing the body”, so the task pane now uses `POST /api/addin/analyze-json` with `{csv, highlight_cap}`; multipart remains for desktop compatibility. JSON analysis was verified through the public tunnel; final Excel-web Highlight/Clear retest is pending.
- Standing owner rule: every app change updates `AGENT_BRIEF.md` and the relevant GitHub Markdown docs in the same commit.

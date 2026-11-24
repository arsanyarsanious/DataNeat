# DataNeat

> **Agent handoff:** read [AGENT_BRIEF.md](AGENT_BRIEF.md) first for the complete current architecture, feature inventory, security findings and unfinished work.

> **Current project context (21 October 2026):** see [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for the complete verified AI handoff. Some historical sections below still describe retired Advanced screens or older preparation behavior. Current source and PROJECT_CONTEXT.md take precedence; do not initialize the current UI through the legacy editor startup route.

Local, guided spreadsheet cleaning. Interactive spreadsheet is the default; Advanced analysis remains optional. No account, payment card or external AI service is needed. Nothing in this update deploys the application publicly.

## Start on Windows

Install Docker Desktop with Linux containers enabled. Double-click **Start DataNeat.vbs** in this folder. It starts Docker Desktop when available, builds/starts the existing `dataneat` Compose services, checks frontend and backend readiness, then opens http://localhost:3000/. First build can take several minutes. A mutex prevents duplicate launcher runs; Compose reuses the existing containers and storage volume. Errors are shown in a dialog and recorded in `dataneat-startup.log`.

Docker remains required. The launcher does not install Docker or a separate native runtime. Keep the services running while using localhost.

Manual alternative:

```powershell
docker compose -p dataneat up -d --build backend frontend
```

Readiness-only check:

```powershell
powershell -NoProfile -File .\Start-DataNeat.ps1 -CheckOnly
```

Stop with `docker compose -p dataneat stop`. Do not remove the storage volume unless you intend to erase stored uploads. Backend documentation: http://localhost:8000/docs.

## Formats and preservation boundaries

CSV and XLSX, up to 20 MB by default, 100,000 rows and 200 columns. CSV text, leading zeros and literal missing markers are retained on import. XLSX uses the selected worksheet, preserves text IDs and simple numeric zero-padding formats, and reads formula text without executing it.

**The output is a cleaned data table, not a preserved Excel workbook.** Formatting, charts, macros, merged cells, other worksheets and executable formulas are not retained. Formula-looking strings are escaped on export. Excel numbers may already have lost precision before upload: keep long IDs as text. Native Excel date values are read; date normalization still requires a reviewed action. Unicode text is preserved in CSV/XLSX and JSON; Arabic PDF shaping is not offered. The PDF report interface is English.

## Interactive workflow

1. Upload a file. New interactive sessions open with the original values; no preparation is applied silently.
2. Open **Preparation**. Outer whitespace trimming and internal whitespace collapsing are separate controls. Choose global missing markers, override markers per column, or exclude a column. Review counts and examples, then apply the reviewed decision.
3. Open **Column rules** to declare intent: text, identifier, numeric, currency, percentage, boolean or date. Add required/unique/allowed values, bounds or wildcard text patterns. Rules identify issues and do not convert values. Wildcards: `*` any text, `?` one character, `[0-9]` a digit; this is not arbitrary regular-expression execution. Currency rules compare literal labels, not exchange rates. Percentage bounds use percentage points; specify how bare numbers are interpreted. Date interpretation is explicit.
4. Highlighted cells show invalid findings, inconsistencies and review suggestions. Rare values and outliers are not automatically wrong. Use **Mark this finding as valid / Ignore** for a reviewed cell; undo the ignore step to restore the finding. An ignore is tied to its row, kind and current value when specified.
5. **Unify text values** lists distinct text values and frequencies. Suggested spelling groups use local string similarity among at most 1,000 frequent strings up to 100 characters. Select a suggestion, edit the candidates and final spelling, then explicitly apply. Suggestions do not establish semantic or transliteration equivalence.
6. Issue navigation includes only kinds actually present in the selected column across all pages. Next Issue visits different kinds and stops at the end. The legend is optional. Comma separators affect preview display only.
7. Confirmed actions appear in history. Undo replays remaining decisions against a preserved baseline. If a later step depends on the removed step, the job fails without committing and explains the conflict.

Preparation is a transformation of the current working copy. Changing settings later does not restore earlier changed values; undo the preparation step. Empty cells and actual null values remain missing. Excluding a column preserves literal codes such as `NA` from missing-marker interpretation.

Existing uploaded files and older edits are preserved as a migration baseline. They are not silently re-prepared. Older sample-only history is labelled: complete per-cell audit and enhanced undo begin with new workflow decisions. Baseline steps cannot be removed by enhanced undo. The original upload remains available until expiry.

## Background processing and recovery

Enhanced cleaning, undo/replay, reanalysis, recipe previews/applications and export generation use bounded background jobs. Stage indicators are indeterminate unless there is a real count of recipe steps. Cancellation is cooperative: the current calculation may finish before stopping, but uncommitted work is discarded. Changes commit atomically only if the expected revision is still current. Once a commit completes, use Undo instead of cancellation.

Jobs and export status are stored locally. Refresh in the same tab resumes the saved job and reloads the working revision. A service restart cannot resume in-memory calculations: interrupted jobs fail explicitly; an already committed enhanced revision can be recovered. Advanced preview/cleaning jobs also expose cancellation and persist completed results. The UI retains its Advanced review-before-selection controls.

Column annotations are cached after enhanced analysis/commits and sliced during paging. Initial uploads still parse/profile before the first workspace opens. Analysis uses server threads and does not hold the global storage lock during full-column issue navigation.

## Recipes and batch cleaning

**Recipes** exports/imports version 1 JSON without accounts. A recipe contains reviewed preparation, column rules, approved text mappings and transferable whole-column operations. It intentionally excludes row-specific replacements, issue-clearing replacements and ignored findings. Recipe export is not a record of all manual edits.

Compatibility checks report missing/extra columns, unmatched mapping sources and unmapped values that will remain unchanged (up to 50 examples with a total). Preview before applying. Mean, median and mode are recalculated on the destination file; constants remain fixed. Values absent from a file do not force unrelated changes.

**Batch** uploads files separately, previews each with a selected recipe, applies only preview-compatible files, isolates failures, and provides individual Excel/PDF exports plus a JSON batch summary. Files are never combined. Uploaded batch file IDs, recipe and job status recover from same-tab session metadata after refresh. Files not yet uploaded must be selected again. Committed files remain server-side and owner-scoped until expiry. Batch currently uses the first worksheet for XLSX; use single-file upload to select another sheet.

## Review and exports

**Review** searches the complete enhanced cell-change log and filters by column, action and revision. Removed rows include their original cells. Counts are per operation, not unique changed cells across the entire history. Rule/ignore decisions are in history even if no cells changed.

**Exports** prepares CSV, XLSX, an English PDF, a complete JSON change log, or a ZIP review package in the background. The package contains report.pdf and recipe.json; changes.json is opt-in. It does not contain the full original upload. Reports, recipes and logs can still reveal column names, original/corrected values and examples: share only with authorized reviewers. PDF examples are nonexhaustive; machine-readable change logs provide complete enhanced-workflow records.

## Privacy and retention

All processing occurs on the server running DataNeat (your computer in the default setup). No data is sent to external AI services. Files and results are owner-session scoped, become inaccessible after 24 hours, and expire during cleanup. Delete file removes its upload and stored associated job/output artifacts. Jobs cannot retrieve an export once its parent upload is inaccessible.

Google/email authentication remains optional and is not enabled by this work. Live collaboration, cloud sync, external connectors and public deployment remain out of scope.

## Validation

Backend tests:

```powershell
docker run --rm --mount "type=bind,source=C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable\backend\tests,target=/app/tests,readonly" dataneat-backend python -m pytest tests -q -p no:cacheprovider
```

Frontend production validation: `docker compose -p dataneat build frontend`.

Tests cover synthetic known errors and legitimate exceptions, session isolation, stale revisions, cancellation, preparation reversal, rules, mapping replay, recipes and export boundaries. They are regression checks, not evidence of real-world detection accuracy. Independent user benchmarking and observed task sessions are still needed.

See IMPLEMENTATION.md and VALIDATION.md for the delivered checks. Earlier technical notes are retained in docs/legacy-README.md for reference; this README describes the current workflow.

## Native development

Requires Python 3.12+ and Node.js 22+. Create a virtual environment and install `backend/requirements.lock.txt` plus `backend/pdf-dependencies.lock`. Run `python -m uvicorn app.main:app --app-dir backend --reload --port 8000` and `npm ci --prefix frontend`, then `npm run dev --prefix frontend`. Native processes do not automatically read .env. Docker Compose reads .env using .env.example as the reference.

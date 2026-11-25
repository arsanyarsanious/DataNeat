# DataNeat — Complete Agent Handoff Brief

**Snapshot:** 2026-11-24, ~20:35 Africa/Cairo
**Repository:** https://github.com/arsanyarsanious/DataNeat — `main` (check `git log` for the latest commit; this brief was authored around `67ebc04`)
**Working copy:** `C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable`
**Public app:** https://arsany.pythonanywhere.com/
**Product owner:** Arsany Arsanious (`arsanyarsanious@gmail.com`); communicates in
Egyptian Arabic, accepts English deliverables; prefers free/no-card hosting,
visible outcomes and screenshots, and explicit approval before broad changes.

This is the canonical handoff. Older documents are valuable but contain
historical or stale statements; when they conflict, trust the code and this
brief. `PROJECT_CONTEXT.md` has the long chronological record (§1–§44) and
`docs/git-workflow.md` documents pushes. **`SECURITY_AUDIT.md` is the current
security review** (findings, evidence, authorization tests and remediation
order); read it before exposing any API or companion service.

**Standing owner rule:** every change to the app must also update this brief and
the relevant GitHub Markdown (`README.md`, `PROJECT_CONTEXT.md`, feature docs
under `docs/`) in the same commit. Never leave the brief behind the code.

---

## 1. What DataNeat is

A local-first spreadsheet cleaning SaaS. The user uploads a messy CSV/XLSX,
sees detected issues, chooses corrections, reviews changes, and exports a
cleaned table plus a readable audit report. Core promises:

- **The original upload is always preserved.**
- **No silent cleaning.** Entering the spreadsheet never rewrites values.
- Every applied change is recorded, revision-checked, and undoable.
- Issues are review flags, not declarations that a value is wrong.
- Ambiguous cases (dates, bare percentages, units, merges) require an explicit
  decision; the engine never guesses.
- The public beta uses Supabase auth and PythonAnywhere; local use works without
  an account.

The app is intentionally more “careful data review” than “one-click magic”.

---

## 2. Current status snapshot

| Area | State |
|---|---|
| GitHub | `main` (check `git log`; the security/P0 changes are committed and pushed), clean working tree, remote configured with credential-manager auth |
| Web app (live) | https://arsany.pythonanywhere.com/ — PythonAnywhere free, one worker, 60s proxy timeout, 512 MiB disk |
| Live limits | 5 MiB upload, 15,000 rows, 75 columns, 250,000-cell analysis budget, 300 MB snapshot budget, 200 stored records; 30 saved files / 40 MiB per account |
| Live auth | Supabase enabled, Google sign-in enabled; `REQUIRE_AUTH=true` fail-closed guard deployed; public share routes only auth bypass |
| Live deployment | **Behind GitHub main.** On 2026-11-25 a minimal P0 patch of the live `main.py` removed diagnostics/disk fields and added the auth guard; the live config had `DIAG_TOKEN`/`ERROR_LOG` removed and `REQUIRE_AUTH` enabled. The full merged backend (workflow/add-in/etc.) is still not deployed. Live health now returns only status/limits. |
| Backend tests | **739 passed** (41 test files), including P0 auth-guard and diagnostics-removal tests |
| Frontend | TypeScript + `CLOUDFLARE_EXPORT=1` production build last passed after the history merge; Excel add-in has no frontend build step |
| Excel add-in | Tier L **read-only preview** implemented locally. Real Excel task pane loads and analysis works; highlighting is implemented but was blocked on this machine by unlicensed Excel / Protected View. Not installed for other users yet. |
| Excel on the web | Analyze works in Excel web (sheet with 5,555 rows / 36 columns returned 31,823 issue cells). Highlight initially hit Office’s request-payload limit because thousands of ranges were sent in one sync; fill/backup/clear are now batched 200 ranges per sync. Retest highlight pending. |
| Excel manifest | Validated with Microsoft’s `office-addin-manifest`; SourceLocation `https://localhost:9443/taskpane.html` |
| Deployment status file | `C:\Users\Arsany Arsanious\Documents\Codex\outputs\dataneat-deployment\DEPLOYMENT_STATUS.md`; updated for the P0 patch, but full-live reconciliation remains |
| Local add-in companion | Can run on `https://localhost:9443`; certificate trusted for current Windows user; test Excel workbook exists in the workspace (not repo). The public tunnel is stopped. |

**Immediate source-of-truth caveat:** deploy decisions must compare repo `main`
with the live backend/static build. Do not assume live is current.

---

## 3. Complete feature inventory

### 3.1 Pages and entry points

- `/` cover (dark-first premium design, sample corrections, theme toggle)
- `/login` Supabase email/password + Google sign-in, local-workspace fallback
- `/workspace` upload → Explore → Clean → Imputation → Export
- `/files` saved account files (rename, delete, continue)
- `/guide` searchable 15-section handbook
- `/privacy` policy
- `/share/[token]` public read-only review page + PDF report
- `/api/*` FastAPI backend; FastAPI Swagger at `/docs`
- Excel add-in task pane (`excel-addin/taskpane`) served by the local companion

### 3.2 Import and preservation

- CSV and XLSX; multi-sheet XLSX worksheet picker; hidden sheets unavailable.
- Encoding detection, delimiter inference, duplicate-header renaming, header
  adjustment reporting.
- Leading-zero IDs and text preserved; XLSX reads formula **text**, never
  executes formulas.
- Excel output is a cleaned data table, not a formatted workbook copy: charts,
  macros, merged cells, other sheets and formulas are not preserved in web
  export.
- Original upload bytes and metadata remain separately preserved until expiry.
- Limits are environment-driven: bytes, rows, columns, cells, storage,
  stored-file count, account files.

### 3.3 Profiling and type detection

Detected types include text, category, numeric/integer/decimal, identifier,
phone, email, boolean, date, datetime, time, duration, location, coordinate,
currency, percentage, URL, IP, and structured/delimited data. Legacy `salary`
is accepted only for compatibility and displayed as Number.

Each column profile includes counts, missing percentage, uniqueness, sample
values, detected type/confidence, issues, markers, rules intent, distribution
statistics, missing pattern and imputation recommendation.

### 3.4 Issue families

- missing values and recognized missing-value labels (`NA`, `null`, `-`, etc.;
  configurable markers per column)
- whitespace; capitalization/case inconsistency
- type mismatch; odd/unusual values
- dates: invalid calendar dates, ambiguous day/month, mixed formats
- time, duration, clock formats
- currency notation, percentage notation, bare-percentage scale
- symbols/units, phone format, email syntax
- boolean label inconsistency
- data-format interpretation (numbers/fractions/locale, units, Unix/Excel
  numeric dates, named timezones, lists/JSON, coordinates, URLs, IPs)
- duplicate rows
- column rules: required, unique, allowed values, minimum/maximum, date range,
  negative policy, wildcard text pattern
- cross-column relationship findings
- outliers
- percentage-scale review issue

Issue counts are real whole-file counts; cell annotations are computed with
`annotate()` and used by header badges, navigation and the correction panel.

### 3.5 Manual cleaning (main flow)

- Explore shows a data preview, real metrics, and one manual-review card.
- The spreadsheet opens immediately; Guided cleaning and Automatic cleaning are
  available in the sheet at any time.
- The “Review suggested fixes” entry/gate was removed per owner request; legacy
  quick-clean components may remain but must not become the entry point again.
- Clicking a flagged cell opens a correction panel with:
  - Suggested correction + Before/After
  - “Change correction” / More options
  - issue-specific action list only (phone gets phone normalizer + manual
    correction; currency gets currency; URL gets URL; email/type mismatch only
    manual; this was fixed and verified)
  - scope: cell, column, issue, issue in selected columns, matching values,
    cross-column, invalid dates
  - required parameters, blockers, acknowledgement, preview and Apply
- Issued cells can be marked valid/ignored; undo restores the finding.
- Column settings dialog: data type, rules, negative policy, cleaning action,
  Insights, Cleaning plan; percentage bare-scale declaration; AI type suggestion.
- Unify text values: local spelling similarity; max 1,000 frequent strings,
  ≤100 chars; explicit apply; no semantic/transliteration guessing.
- Issue navigation/legend: next issue, different issue types, column filtering,
  page navigation; 48px virtual rows.

### 3.6 Guided cleaning

One issue type/column at a time using whole-file counts. Fix opens the normal
correction scope; partial fixes update counts and keep the same issue. Skip and
Next move the walkthrough, not data. Progress is tab-scoped. Completion panel
distinguishes reviewed/skipped/resolved and remaining issue groups. No
“Review suggested fixes” completion button (owner removed it).

### 3.7 Automatic cleaning (website)

Optional survey opened from the workbook toolbar; it does not run on upload.
Questions cover trim whitespace, boolean labels, capitalization, date
interpretation (including day-first/month-first ambiguity resolution), numeric
missing-value policy (mean/median/mode/constant/leave empty), and duplicate-row
removal (separate, default keep). Each question supports per-column exceptions.
Applied operations are audited/undoable, revision-checked and background-run.
Automatic mode is explicit and optional. **Website automatic still supports the
numeric missing-value policy; the Excel add-in plan explicitly forbids
imputation in Excel automatic mode.**

### 3.8 Imputation

- Mean, median, mode, grouped mean/median/mode, constant, directional fill,
  linear interpolation, date sequence, date median, KNN, iterative imputation.
- Missing-value readiness gates: unresolved issue kinds must be reviewed or
  explicitly acknowledged; identifier/literal-marker protection.
- Date median estimates a chronological midpoint, not a verified event;
  acknowledgement required; floor/nearest/ceil rounding.
- Percentage mean/median requires a declared bare scale; ratio values are
  scaled for calculation; marked values stay percentage points.
- Imputed cells marked with provenance, excluded as donor observations for later
  estimates; manual replacement clears provenance; undo restores it.
- Failed groups are isolated; nothing is committed unless the job completes.

### 3.9 Reviewed quality tools

Available through “More cleaning tools”/quality workbench:

1. **Related column rules** — up to 30 named rules; arithmetic comparisons
   (+, −, ×, ÷), conditional required values, numeric tolerance, explicit
   ambiguous-date handling. Saving adds findings; recalculation/clearing is a
   separate reviewed action; no arbitrary expression evaluation.
2. **KNN & Iterative imputation** — 1–8 numeric helpers; robust scaling;
   deterministic holdout MAE vs median baseline; sample caps (2,000 donors,
   10,000 target cells, 8 helpers, batch 128); explicit acknowledgement.
3. **Similar records** — 2–5 match fields, threshold, blocking column;
   sorted-neighborhood capped at 20,000 pairs; up to 100 candidates; manual
   merge, row retention, conflict choices; audit/undo.
4. **Outlier review** — IQR or normalized MAD, optional grouping; keep, clear or
   cap at displayed bounds; review first; no automatic deletion.

These decisions are audit/undoable but excluded from transferable recipes.

### 3.10 History, undo, rules and recipes

- Every workflow decision is versioned; record has `editor_revision`.
- Workflow jobs use expected-revision CAS; stale revisions return a conflict.
- Undo/replay recomputes surviving decisions against a preserved baseline;
  dependencies that conflict fail without committing.
- Review/change log supports filtering; export logs can be generated.
- Recipes (JSON version 1) export reviewed preparation, rules, text mappings
  and transferable whole-column operations; manual row-specific edits and
  reviewed-tool decisions are excluded. Preview/apply has compatibility checks.
- Saved choices (browser, up to 20 × 100 actions) store notation actions only;
  fresh preview required.
- Ignore/valid decisions and column renames are tracked; rename carries rules,
  preparation overrides and ignored findings.

### 3.11 Exports

- Cleaned **XLSX** table, **CSV**, English **PDF report**.
- Background export jobs with progress/cancel; recovery from same-tab session.
- PDF contains steps, issues, counts, examples and imputation provenance;
  examples are not exhaustive.
- Share review page can stream the PDF.
- Historical README mentions JSON/ZIP packages and batch; verify current UI
  before advertising those as live features.

### 3.12 Read-only share links

- Owner creates `POST /api/files/{id}/share?ttl_hours=168`; default 7 days,
  max 30 days.
- HMAC-SHA256 token over `{version, file id, share epoch, expiry}`; bearer
  secret; not a session cookie.
- Public `GET /api/share/{token}` returns metadata, revision, counts, recorded
  step summaries, issue overview and a 25-row preview.
- Public `GET /api/share/{token}/report` streams the PDF.
- Revocation rotates a per-file share epoch; delete/expiry also invalidates.
- Never exposes editing, deletion, original bytes, workspace or owner session.
- Signing key: `SHARE_SIGNING_KEY` → `STORAGE_SIGNING_KEY` → private
  `STORAGE_DIR/.share-key` (mode 0600).

### 3.13 Optional AI assistant (BYOK)

- `POST /api/assist`; consent required; server-side kill switch
  `AI_ASSIST_ENABLED`.
- Presets only: `gemini`, `groq`, `openrouter` (fixed base URLs, preventing SSRF).
- Server selects up to 12 short sample values from the working copy; client
  cannot submit samples.
- Key is used for the request only, not stored, echoed or logged.
- Suggestions: type suggestion validated against vocabulary, or plain-text
  explanation. Applying a type is a normal reviewed rules decision.
- PythonAnywhere free outbound whitelist must include provider hosts manually;
  otherwise assistant fails with retry message.

### 3.14 Accounts, saving and usage

- Supabase Google/email auth; access token stored in httpOnly cookie
  `dataneat_auth`; middleware verifies for all non-public `/api` paths.
- Account file list, rename, delete, continue cleaning, storage usage.
- Guest/session files temporary 24h; saved files persist until deleted.
- Usage counters: sign-in, upload, clean, editor start/fix, download; 90-day
  retention; admins controlled by `ADMIN_EMAILS`.
- Account storage quotas: env `MAX_ACCOUNT_FILES` (100 default),
  `MAX_ACCOUNT_STORAGE_MB` (1024 default); live beta 30 / 40 MiB.
- Temp snapshots stored locally or in Supabase CloudStore depending on
  `CLOUD_STORAGE`; local Store uses pickle + retention JSON; CloudStore uses
  signed/compressed payloads and Supabase RPC.

### 3.15 Capacity and limits

- Live: 5 MiB, 15k rows, 75 columns, 250k-cell analysis budget, 300MB snapshot
  budget, 200 records.
- Configurable env: `MAX_UPLOAD_MB`, `MAX_UPLOAD_ROWS`, `MAX_UPLOAD_COLUMNS`,
  `MAX_WORKFLOW_CELLS`, `MAX_STORAGE_MB`, `MAX_STORED_FILES`,
  `MAX_ACCOUNT_FILES`, `MAX_ACCOUNT_STORAGE_MB`, `CLEANING_WORKERS`.
- Analysis > 40k cells is off-request: upload returns `analysis_pending`; poll
  `GET /api/files/{id}/analysis` (202 pending / 200 ready); hosted config sets
  `ANALYSIS_SYNC_CELLS=0` so every hosted upload returns immediately.
- Upload response uses a local-first temporary snapshot; the background
  analysis performs the durable cloud commit. This trades crash durability for
  fast upload; a lost worker can lose a pending temporary file.
- PythonAnywhere cuts requests at 60s and allows 100 MB bodies; the app's own
  limits are lower.

### 3.16 Design and responsive behavior

- Premium dark-first UI from `frontend/app/premium-theme.css` (last import);
  light theme retained and restyled.
- Self-hosted Inter Variable (`frontend/app/fonts/InterVariable.woff2`, OFL);
  no runtime font request; tabular numerals in the grid.
- Palette: `#0B0F19` bg, `#111827` surface, `#1F2937` panel, `#374151` border,
  `#10B981`/`#34D399` mint, `#F9FAFB`/`#D1D5DB` text, `#9CA3AF` muted.
- Dark sidebar in both themes, 3px active rail, mint primary gradient with dark
  ink, 14px cards, 16px modals, pill tabs, blurred backdrops, 180ms transitions.
- **Spreadsheet row/cell height is fixed at 48px** for virtualization; do not
  change it without updating the scrolling/virtualizer.
- Correction panel clamped away from the fixed sidebar.
- Cover, login, workspace, files, guide, privacy and share all use the system.
- Reviewed in headless Chromium at 1440/950 and 390px mobile, dark and light.

### 3.17 Excel add-in (Tier L preview — new)

- `excel-addin/` at repo root; Windows-only local companion.
- `manifest.xml` sideload task pane, `ReadWriteDocument`, SourceLocation
  `https://localhost:9443/taskpane.html`; validated by Microsoft validator.
- `companion/run.ps1` runs the existing FastAPI app with:
  - `PYTHONPATH=<repo>/backend`, `STATIC_DIR=<taskpane>`,
    `STORAGE_DIR=%LOCALAPPDATA%\DataNeat\excel-addin\storage`
  - TLS cert/key under `companion/certs` (gitignored)
  - auth disabled (empty Supabase env), AI off, `MAX_UPLOAD_MB=60`,
    `MAX_UPLOAD_ROWS=1,000,000`, `MAX_UPLOAD_COLUMNS=100`,
    `MAX_WORKFLOW_CELLS=3,000,000`, `ADDIN_MAX_CELLS=3,000,000`,
    `ANALYSIS_SYNC_CELLS=0`
- `companion/setup.ps1` creates `.venv`, installs
  `requirements.txt` (backend requirements + cryptography), generates/trusts a
  localhost certificate. Python 3.12 preferred; fallback to default Python.
- `companion/certs.py` generates a self-signed localhost cert and adds it to
  the current user’s Root store.
- Task pane: reads active worksheet used range in 15k-row chunks, sends displayed
  cell text as CSV to `POST /api/addin/analyze`, shows metrics/issue table,
  highlights up to **10,000** flagged cells as fill colors, stores original
  fills in Office document settings (or localStorage fallback) for Clear.
- Backend `services/addin.py`: read-only endpoint, max 3M cells, profiles with
  the shared engine, annotates in 20k-row chunks, returns compact cells capped
  at the requested highlight cap (server max 200k; taskpane asks 10k).
- Verified in real Excel 365 desktop: task pane loaded at localhost, analysis
  returned 17 flagged cells across 6 columns. **Highlighting could not be
  visually verified on this machine** because Excel is unlicensed/protected;
  Office.js formatting returns “You cannot perform the requested operation”.
  Analysis works; COM formatting works, so the block is Excel’s add-in write
  gate, not the analyzer. The task pane now explains this.
- Not deployed as an installer or packaged app. It relies on Python and a
  locally trusted cert. No automatic cleaning/corrections yet. Tier XL
  (10M cells) is only a plan.
- **Excel on the web testing path:** `companion/web-tunnel.ps1` starts a
  temporary Cloudflare quick tunnel to the local companion and generates
  `excel-addin/generated/manifest.web.xml`. Excel web can sideload that manifest
  without a desktop license. The URL changes per run and is gitignored. The
  companion allows `*.trycloudflare.com` origins via `CORS_ORIGIN_REGEX`; web
  mode uses 5k-row batches, a 1M-cell cap and a 5k highlight cap.
  - The Excel-web task pane **loads** and its initial Analyze reached the
    backend, but Office web's multipart `FormData` path produced FastAPI
    “There was an error parsing the body”.
  - The task pane now sends JSON to `POST /api/addin/analyze-json`
    (`{csv, highlight_cap}`); the multipart `/api/addin/analyze` endpoint is
    retained for desktop/compatibility. JSON analysis is verified through the
    public tunnel with Chromium and with a real Excel-web task pane request.
  - Final in-Excel-web highlight/clear verification is still pending.
  - Excel web accepted Analyze on a 5,555-row × 36-column sheet (31,823 issue
    cells), then rejected the first Highlight attempt with Office’s
    “request payload size has exceeded the limit”. Fill application, original
    fill backup, and clear/restore are now processed in **200-range batches**
    with a sync after each batch. Reopen the task pane and retest.
  - See `docs/excel-addin-web.md`.

---

## 4. Architecture

### 4.1 Stack

**Frontend:** Next.js 16.4 (App Router), React 19.2, TypeScript 5.8,
Tailwind 4.1 + large hand-written CSS layers, Radix Slot, class-variance-authority,
lucide-react, TanStack Table, Supabase JS, Playwright. Static export via
`CLOUDFLARE_EXPORT=1` (no Next server in production).

**Backend:** Python 3.12, FastAPI 0.143, Starlette 1.7, Pydantic 2.14,
pandas 2.2.3, numpy/scipy/scikit-learn 1.9.1, openpyxl 3.1.5, phonenumbers,
ReportLab (PDF deps lock), httpx, Uvicorn, pytest 9.

**Auth/data:** Supabase (auth, PostgreSQL tables, RPC/RLS, storage), Google
OAuth. **Hosting:** PythonAnywhere free ASGI (one worker), file static serving
through FastAPI; optional Render/Docker configs exist but Docker is unusable in
this dev sandbox. **Excel:** Office.js + local TLS FastAPI companion.

### 4.2 Frontend structure

- `app/layout.tsx` imports all CSS globally, with the premium layer last.
- `app/workspace/page.tsx`: upload, analysis polling, workbook picker, state,
  sidebar, Explore/Imputation/Export orchestration.
- `components/interactive-sheet.tsx`: the huge sheet/state machine; correction
  panel, guided/automatic modals, drawer, tools, history, results.
- `components/column-settings.tsx`, `data-format-controls.tsx`,
  `phone/currency/percentage/symbol/date controls`.
- `components/quality-workbench.tsx` + four tool components.
- `components/account-access.tsx` (Supabase session, login UI, account actions).
- `lib/types.ts` (`api()` helper, shared types), `lib/column-data-types.ts`,
  `lib/imputation-*.ts`.
- Session storage keys per file for flow state, job recovery, downloads, etc.
  Theme/sidebar stored in localStorage. `dataneat-theme` default dark.

### 4.3 Backend structure

`main.py`: middleware/auth/rate limits/CORS/body limit, upload/analysis, workspace/preview/editor/editor-fix/undo, jobs/workflow init, exports, health, auth guard, static mount. Installs services at bottom.

`core/`:
- `file_parser.py` CSV/XLSX parsing and limits
- `profiler.py`, `type_detector.py`, `semantic_types.py`, `issue_detector.py`
- `interactive.py` annotations and fix proposal
- `workflow.py` decision model, CAS/replay/undo
- `cleaner.py`, `automatic_cleaning.py`, `cleaning_plan.py`,
  `suggested_cleaning.py`
- `imputation.py`, `imputation_readiness.py`, `model_imputation.py`
- `currency.py`, `percentage.py`, `phone.py`, `symbols.py`, `clock_time.py`,
  `duration.py`, `negative_values.py`, `date_analyzer.py`,
  `date_sequence.py`, `data_formats.py`
- `cross_column.py`, `record_matching.py`, `outlier_review.py`,
  `quality_tools.py`
- `validator.py`, `pdf_report.py`, `xlsx_presentation.py`,
  `sheet_navigation.py`, `common.py`

`services/`:
- `storage.py` local Store (pickle snapshots, retention/expiry, jobs)
- `cloud_storage.py` CloudStore/Supabase signed compressed snapshots
- `identity.py` Supabase verification + usage counters
- `account_files.py` save/list/rename/delete/quota
- `sharing.py` read-only HMAC links
- `ai_assist.py` BYOK provider calls
- `workflow_jobs.py` job runner, revision CAS, recovery
- `addin.py` read-only Excel analysis
- `static_site.py` exported SPA static mount
- `limits.py` body-limit middleware

### 4.4 API catalog (current repo)

Public/non-auth paths: `/api/health`, `/api/auth/config`,
`/api/auth/session`, `/api/auth/logout`, `/api/share/{token}`,
`/api/share/{token}/report`. Diagnostics routes were removed 2026-11-25.

Key routes:
- `POST /api/files/upload`, `/inspect-workbook`
- `GET /api/files/{id}/analysis` (202 pending / 200 ready)
- `GET /workspace`, `/profile`, `/preview`, `/issues`, `/invalid-dates`
- `POST /editor/start`, `GET /editor`, `/editor/compare`, `/editor/search`,
  `/editor/next-issue`, `/editor/scope-counts`, `/editor/text-values`,
  `/editor/status`, `/editor/download`
- `POST /editor/fix`, `/clean`, `/preview-cleaning`, `/undo/{change_id}`
- `GET /cleaning-plan`, `/workspace`, `/workflow/init`, jobs
- `POST /workflow/jobs` etc. via workflow_jobs service
- `GET /jobs/{id}`, `/jobs/{id}/cancel`, `/jobs/{id}/results`,
  `/jobs/{id}/download`
- account files `/api/account/files` through `account_files`
- `/api/files/{id}/share` GET/POST/DELETE; public `/api/share/{token}`
- `/api/assist`
- `/api/addin/analyze` (multipart) and `/api/addin/analyze-json` (Excel-web path)
- `/api/admin/usage` (admin only)
- `/api/auth/me`, `/api/auth/sign-in-event`
- No diagnostics endpoints; `/api/health` returns status/limits only

### 4.5 Revision/workflow invariants

- Every working copy has `editor_revision`; clients send expected revision.
- Workflow job reads record under lock, verifies revision, applies decisions to
  an isolated copy, re-profiles, then atomically saves under `store.lock`.
- Jobs are revision-scoped, cancellable cooperatively; uncommitted work is
  discarded. Committed steps undo by replay from the preserved baseline.
- `analysis_schema_version` is **10**; bumping it invalidates cached profiles
  without changing data/history. Legacy non-workflow records use schema 5.
- Original upload bytes remain separate from the editor DataFrame.
- Cloud snapshots are signed/compressed; local snapshots are pickle files under
  a UUID-only storage root; retention metadata JSON is separate.

### 4.6 Storage/retention

- Temporary uploads expire after 24h (or configured retention) and are purged.
- Saved account files do not expire automatically; deletion is explicit.
- Retention file (`*.retention.json`) tracks session, owner, saved state, expiry;
  save/rename update retention independently of job commits.
- Local Store keeps files + jobs in `STORAGE_DIR`; CloudStore uses Supabase
  `dataneat_files` table and storage RPC; cloud path still writes local cache.
- Usage SQLite in `identity.py` stores content-free events with 90-day cleanup.
- `store.purge()` runs every 60s.

### 4.7 Add-in architecture

```
Excel workbook
  ↕ Office.js (values/text/fill)
Task pane (taskpane.js + HTML/CSS)
  ↕ HTTPS same-origin fetch
Local companion FastAPI https://127.0.0.1:9443
  ├─ existing profiler/annotator (/api/addin/analyze)
  └─ taskpane static assets (STATIC_DIR)
```
The companion is single-user localhost; it disables Supabase auth. A local
certificate trusted for the Windows user enables HTTPS. `manifest.xml` points
at the localhost task pane. No cloud data path exists in this preview.

### 4.8 Deployment topology

- Primary live: PythonAnywhere ASGI `dataneat` app, one worker, unix socket,
  `/home/ARSANY/dataneat/backend`, static `/home/ARSANY/dataneat/public`,
  launcher `/home/ARSANY/dataneat-launch.py`, config
  `/home/ARSANY/.dataneat-config.json` mode 0600.
- PythonAnywhere free proxy: **60s request timeout**, up to 100 MB bodies.
  Outbound proxy `http://proxy.server:3128` is required for Supabase; free
  whitelist blocks arbitrary AI hosts until manually allowed.
- Docker Compose (`backend` + `frontend`) exists and is the documented local
  path, but Docker is unusable in this development sandbox; native venv used.
- `render.yaml` exists with different (2MB/10k/50) limits; not the current live
  host.
- Static export is served by FastAPI (`STATIC_DIR`) for one-origin deployment.
- Workspace deployment helpers (outside repo):
  `pa_deploy.py`, `pa_static.py`, `pa_phase_a.py`, `pa_config.py`,
  `pa_whitelist.py`, `pa_date_fix.py`. PythonAnywhere token lives in
  `Documents\Codex\private\dataneat-pythonanywhere-api.txt`; never print.
  Reload endpoint requires trailing slash.
- Deployment status: `C:\Users\Arsany Arsanious\Documents\Codex\outputs\dataneat-deployment\DEPLOYMENT_STATUS.md`.

---

## 5. Security and privacy

### 5.1 Authentication

- Supabase issues access tokens; frontend calls `/api/auth/session` to set
  `dataneat_auth` httpOnly, SameSite=Lax, secure when `COOKIE_SECURE=true`.
- Middleware verifies token for all `/api` except public paths. Invalid/missing
  tokens get 401 JSON; account ID is hashed into a stable session ID.
- Logout deletes the cookie; token remains valid at Supabase until expiry
  (`max_age=3600`). No server-side revocation list.
- Admin routes require `ADMIN_EMAILS`.
- Session cookie `dataneat_session` is a UUID with httpOnly/samesite and a
  1-year max age; guest ownership scoping.

### 5.2 Ownership/access

- Uploaded record has `session` and optional `account_owner`.
- File routes call `file_record(file_id, request)` which loads with the current
  session; saved/account list filters owner.
- Saved files include original/current/history; quota and ownership checks.
- Share tokens independently authorize read-only metadata/PDF only.
- Cloud RPC uses owner/session filters; local storage path rejects non-UUID keys.

### 5.3 Secrets

- `.env` and `.venv`, certs, keys, build output ignored by `.gitignore`.
- Supabase service key/HMAC/PA token/API keys live outside repo; deployment
  scripts read private files.
- AI provider key is transmitted per request, not stored/logged/echoed.
- GitHub auth is via Windows Credential Manager; no token in repo.

### 5.4 Share links

- HMAC bearer tokens; 7-day default, 30-day max; per-file epoch revocation.
- Token payload versioned, signed, checked for expiry/file/owner epoch.
- Public routes GET-only; 25-row preview + PDF may reveal values; owner warning.
- Signing key falls back to a private file with mode 0600.

### 5.5 AI assistant

- Fixed provider base URLs only; no arbitrary URL (SSRF guard).
- Consent flag and server kill switch; key not stored; sample data only from
  server-selected working copy; suggestions never auto-applied.
- Hosted PA needs whitelist entries for provider hosts.

### 5.6 Local Excel companion

- Binds `127.0.0.1`, HTTPS with a self-signed localhost certificate trusted in
  the current user’s Root store; private key is an unencrypted file under
  `excel-addin/companion/certs` (gitignored).
- **Auth is disabled** in the companion; no bearer/CSRF token on its API. Any
  local process/page that can reach `https://localhost:9443` can invoke
  analysis/upload. Threat is local-only, but should be hardened with an
  add-in token, Origin check, and perhaps per-launch secret.
- Task pane has `ReadWriteDocument`; it can edit the workbook (intended).
- The web-tunnel path exposes the unauthenticated local companion through a
  temporary public `*.trycloudflare.com` URL. The CORS regex allows any
  trycloudflare subdomain, not only the current tunnel. Treat it as a temporary
  test channel only; stop it after use and do not send confidential data.
- `saveBackup` of original fills uses Office document settings (size-limited);
  large backups fall back to localStorage or fail restore.
- Certificate is generated as a self-signed CA (`BasicConstraints CA=true`);
  should be replaced with a narrow leaf certificate and documented uninstall.
- Office.js loads from `appsforoffice.microsoft.com`; internet dependency.

### 5.7 Known security issues / cleanup required

**Full review: `SECURITY_AUDIT.md`.** The public Excel-web tunnel and
unauthenticated companion were stopped after that audit; do not restart them
without add-in token auth and exact-origin CORS.

1. **Diagnostics cleanup completed 2026-11-25.** Removed
   `/api/diagnostics/*`, disk fields from `/api/health`, and the entries from
   `public_paths`; removed `DIAG_TOKEN`/`ERROR_LOG` from the live config (token
   capability no longer exists); redeployed and verified minimal health and
   OpenAPI. A future rollback to an old build would reintroduce them; re-check
   after any restore.
2. **Live deployment is behind repo main**; the P0 patch is live, but the full
   merged backend (workflows, add-in endpoint, other changes) is not. Deploying
   it still needs the normal test/browser/rollback process. Compare and verify;
   do not assume.
3. **Add-in companion unauthenticated localhost API**: it was exposed through a
   public quick tunnel during Excel-web testing; the tunnel and companion are
   stopped. Add a per-launch token, exact-origin CORS and protected tunnel
   before reuse.
4. **Self-signed CA cert** and Python dependency/installer not production-grade.
5. **Share/PII**: share tokens are bearer secrets; PDF/preview values visible;
   warn users; limit TTL.
6. **Rate limiting is in-memory per IP**; behind PA proxy client IP handling
   can group users; no account-level rate limit; single worker DoS possible.
7. **CSRF**: state-changing APIs rely on SameSite=Lax + CORS; no anti-CSRF
   token. Hosted origin is one domain; local companion has no CSRF.
8. **Cloud storage fallback**: local-first upload can lose a pending temporary
   file if the worker dies before background commit/analysis.
9. **Single-worker coordination** (`store.lock`, in-memory jobs/rate/editor
   caches) means multi-worker is unsafe; see `docs/host-migration.md`.
10. **README and historical docs are stale** (claim no auth/external AI, old
    limits) and could mislead agents; canonical brief is this file.
11. **Account/token logout** doesn't revoke Supabase sessions server-side.
12. **Excel test host is unlicensed**; highlights not verified; users need a
    licensed/signed-in Excel and editable workbook.
13. **No packaged installer** for the companion; requires Python 3.12 and
    manual cert trust; `.venv` junction on this machine is ignored and not
    portable.
14. **Office.js formatting AccessDenied** may also occur on some licensed
    builds (search results show a broader Excel protection AccessDenied issue);
    if so, fallback may need COM-based formatting (Windows-only) or conditional
    formatting.
15. **Original-fill backup** limited by Office settings; clear may remove fills
    without restore.
16. **No CSP** on taskpane/static app; Office.js CDN is required; consider
    CSP headers for hosted pages.
17. **Authentication fail-open guard implemented 2026-11-25**: `REQUIRE_AUTH=true`
    returns 503 for protected APIs when Supabase URL/key are absent; local
    development/companion defaults to false. Covered by tests; live config
    enables it. Keep it true on any public deployment.

### 5.8 Privacy/retention

- Hosted processing on PythonAnywhere; auth/storage on Supabase; local installs
  process locally.
- Temp 24h; saved until delete; usage 90 days; share links expire/revoke.
- Spreadsheet contents excluded from usage analytics; analytics counts events,
  not values/filenames (filename in saved metadata, not usage).
- No advertising/AI training; optional AI only with user key/consent.

---

## 6. Verification and commands

### 6.1 Backend tests

```powershell
$venv = 'C:\Users\Arsany Arsanious\Documents\deepseek-harness\default-workspace\dnvenv'
$project = 'C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable'
$tmp = 'C:\Users\Arsany Arsanious\Documents\deepseek-harness\default-workspace\tmp'
$env:PYTHONPATH = "$project\backend"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TMP = $tmp; $env:TEMP = $tmp
$env:STORAGE_DIR = "$tmp\test-store"
& "$venv\Scripts\python.exe" -m pytest "$project\backend\tests" -q `
  -p no:cacheprovider --basetemp="$tmp\pytest-run"
```
Latest: **739 passed** (2 pre-existing deprecation warnings).

### 6.2 Frontend typecheck/build

```powershell
$nodeDir = 'C:\Users\Arsany Arsanious\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin'
$node = "$nodeDir\node.exe"
$pnpm = 'C:\Users\Arsany Arsanious\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs'
$env:PATH = "$nodeDir;$env:PATH"
cd 'C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable\frontend'
& $node $pnpm exec tsc --noEmit
$env:CLOUDFLARE_EXPORT = '1'
& $node $pnpm run build
```
Static output: `frontend/out` (66 files historically). No npm in the bundled
runtime; pnpm install uses `--no-frozen-lockfile --dangerously-allow-all-builds`.

### 6.3 Local native web app

```powershell
$env:PYTHONPATH = "$project\backend"
$env:STORAGE_DIR = "$tmp\ui-store"
$env:STATIC_DIR = "$project\frontend\out"
$env:CORS_ORIGINS = 'http://127.0.0.1:8100'
$env:COOKIE_SECURE = 'false'
$env:TMP = $tmp; $env:TEMP = $tmp
& "$venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```
Playwright: set `NODE_PATH=<project>\frontend\node_modules` and run scripts
with the bundled node. Existing QA scripts live in
`C:\Users\Arsany Arsanious\Documents\deepseek-harness\default-workspace`:
`ui_check.cjs`, `ui_dates_check.cjs`, `ui_missing_check.cjs`,
`ui_percentage_scale.cjs`, `ui_premium_check.cjs`, `ui_async_check.cjs`,
`ui_phone_menu.cjs`, `ui_addin_mock.cjs`, `ui_live_premium.cjs`.

### 6.4 Excel add-in commands

```powershell
cd 'C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable\excel-addin'
.\companion\setup.ps1     # first machine/setup; Python 3.12 preferred
.\companion\run.ps1       # serves https://localhost:9443
# Excel: Insert > Get Add-ins > My Add-ins > Upload My Add-in > manifest.xml
# or open the already-registered add-in; task pane URL is printed by run.ps1
```
On this machine only Python 3.13 is installed; `.venv` is currently a junction
to the harness Python 3.12 venv (ignored by git). Do not rely on that for
portable packaging.

### 6.4.1 Excel on the web

```powershell
# window 1
cd 'C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable\excel-addin'
.\companion\run.ps1
# window 2
.\companion\web-tunnel.ps1
# Excel web: Home > Add-ins > More Settings > Upload My Add-in
# select generated/manifest.web.xml
```
The helper prints the temporary public task-pane URL and manifest path. See
`docs/excel-addin-web.md`. It has only been verified through browser/tunnel;
the Excel-web host still needs a signed-in Microsoft account.

### 6.5 GitHub

```powershell
cd 'C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable'
git status
git add -A
git commit -m "Scoped description"
git push origin main
```
Access uses the Windows Credential Manager entry; no token in the repo. See
`docs/git-workflow.md`. The repo was merged with its earlier 30-commit history;
a UTF-8 repair commit fixed mojibake in `cleaner.py`, `interactive.py`,
`test_engine.py`.

### 6.6 Live deployment

Use the workspace scripts (not in repo):
- `pa_deploy.py` upload individual files with backup/verify.
- `pa_phase_a.py` example multi-file deployment.
- `pa_static.py` throttled static upload (429 backoff) + reload + checks.
- `pa_config.py` / `pa_whitelist.py` private config/outbound whitelist.
PythonAnywhere token path is private; never print it. Always verify API health,
public pages, static chunks, and a real upload/login flow after deployment.
The live static build currently **does not include the GitHub merge after the
last deploy**.

---

## 7. Unresolved problems / prioritized backlog

### P0 — do before calling the current work “shipped”

1. **Diagnostics/auth P0 — completed 2026-11-25**:
   - removed `/api/diagnostics/*` endpoints, disk fields from `/api/health`, and
     `public_paths` entries;
   - removed `DIAG_TOKEN`/`ERROR_LOG` from live config (token capability gone);
   - added and tested `REQUIRE_AUTH` fail-closed guard; live config enables it;
   - deployed the minimal P0 patch to the live host and verified health/OpenAPI.
2. **Reconcile live with repo `main`**:
   - the live host is still behind the full repo (workflows, add-in endpoint,
     later features); fetch/diff, run the 739 tests + frontend build + browser
     smoke, then deploy with the normal rollback path;
   - update `DEPLOYMENT_STATUS.md`.
3. **Verify Excel highlighting on a licensed Excel**, and retest the new JSON
   path in Excel web:
   - In Excel web, close/reopen the add-in to pick up the updated task pane;
   - Analyze, then try Highlight/Clear; report the exact error if it still
     fails;
   - On licensed desktop, test the same;
   - if Office.js still returns AccessDenied, diagnose permissions/protected
     mode/conditional formatting/COM fallback.
4. **Decide whether to keep or remove the temporary add-in `.venv` junction**
   and how the preview will be packaged for the “few users” (installer or
   documented Python setup).

### P1 — high-value unfinished work

5. **Excel add-in productionization**
   - Package companion (PyInstaller/installer; bundled Python 3.12; signed).
   - Auto-start / discovery / port handshake; leaf certificate (not a CA);
     uninstall instructions; taskpane caching/versioning.
   - Add a local API token and Origin/CSRF protection; bind only localhost.
   - Add clear error UI for Protected View/read-only/unlicensed.
   - Add range selection or “analyze selected sheet/table” and progress/ETA.
   - Verify Tier L at 1M–3M cells; current local 400k-cell analysis took ~42s
     and the taskpane highlight cap is 10k cells.
6. **Excel add-in Phase 2** — corrections and automatic cleaning from a saved
   profile, no imputation in automatic mode, preview/apply/undo/report, cloud
   opt-in; then Tier XL batch/file-ingestion mode.
7. **Web upload/analysis performance** — analysis remains CPU-bound; large
   files still wait tens of seconds; no fractional progress. Profiler
   optimization or sampling/streaming is the next lever.
8. **Percentage Phase B** — dual-preview dialog for `0.96` as 96% vs 0.96%,
   optional automatic-cleaning survey question; current Phase A uses Column
   settings + review flag.
9. **AI assistant live path** — PythonAnywhere whitelist for provider hosts is
   manual; authenticated live share/AI smoke tests remain.
10. **Cross-worker architecture** — `docs/host-migration.md`: atomic DB revision
    CAS, cross-process locks, job registry, caches, shared rate limits. Do not
    run multiple workers before this.
11. **Docs cleanup** — README and several legacy docs conflict with current
    auth/AI/share/premium behavior; this brief and PROJECT_CONTEXT §43 are the
    current sources. Update README at the next change.
12. **Polish** — “1 issues” grammar, saved-choices suggested-fixes tab,
    residual quick-review components, legacy batch/ZIP docs.

### P2 — product/roadmap

13. Excel XL (10M cells / 100MB): file-based ingestion, streaming analysis,
    200k highlight cap, 16–32GB RAM, batch apply/export fallback.
14. Paid/capacity hosting; PythonAnywhere free renewal/cold starts; paid
    multi-worker host.
15. Public AppSource distribution for the add-in (currently only private
    sideload decision).
16. Additional language/Arabic PDF shaping; current PDF/UI English, UI copy
    English, owner communicates Arabic.

---

## 8. Where to start (for the next agent)

### If continuing the web app

1. Read this file, `docs/git-workflow.md`, `PROJECT_CONTEXT.md` §37–43,
   `docs/upload-reliability.md`, `docs/percentage-scale.md`,
   `docs/premium-ui.md`.
2. Reproduce the backend suite and frontend build with the commands in §6.
3. Inspect `git log --oneline -10` and compare live `/api/health`/pages with
   repo `main`.
4. The P0 diagnostics/auth cleanup is deployed; compare the live minimal patch
   with repo `main`, then deploy the reconciled main to PA using the workspace
   scripts and verify a real login/upload/clean/export.
5. Keep the invariants in §9.

### If continuing the Excel add-in

1. Read `excel-addin/README.md`, `docs/excel-addin-plan.md`, and
   `backend/app/services/addin.py`.
2. Start companion (`excel-addin\companion\run.ps1`), open Excel, sideload
   `manifest.xml`, sign in/license Excel, enable editing.
3. Test analysis; then highlighting; then `Clear highlights`.
4. If highlight fails on a licensed Excel, capture the exact Office.js error
   (`AccessDenied`/“You cannot perform the requested operation”), check
   workbook protection/read-only, and test a minimal `range.format.fill.color`
   write. Avoid claiming visual verification until it is seen.
5. Package the companion for Windows before distributing to “few users”;
   do not rely on the harness `.venv` junction.

### If implementing Tier XL

Follow `docs/excel-addin-plan.md` §5: file-based ingestion via Office.js
`getFileAsync`, streaming profile in the local engine, capped highlights,
batch apply, 16GB+ RAM, and an export-cleaned-workbook fallback. Tier L must be
stable first.

---

## 9. Do-not-break invariants

- Original upload bytes preserved; cleaning applies to a working copy only.
- Never silently rewrite imported values when opening the spreadsheet.
- Revision CAS on every commit; conflicts return explicit errors.
- No guessing for ambiguous dates, bare percentages, units, merges, or
  relationship matches.
- Every accepted change in audit/history and undoable; failed jobs commit
  nothing.
- Fixed 48px spreadsheet row/cell height; virtualization contract.
- Issue menus only show relevant corrections (verified phone/currency/URL/
  boolean/whitespace/email).
- Automatic cleaning (website) is explicit and optional; Excel automatic must
  exclude imputation per owner decision.
- Dark premium design + light theme; self-hosted Inter; no runtime font request.
- Share links read-only, expiring, revocable; bearer secrets.
- AI optional, consent-only, fixed providers, no key storage.
- Secrets never committed; `.env`, certs, build outputs, `.venv` ignored.
- Windows-only Excel add-in for now; no macOS/web claim.

---

## 11. Tooling inventory

| Tool | Use |
|---|---|
| DeepSeek Harness (DSH) agent environment | all edits, pwsh, file tools, subagents |
| PowerShell 7 / Windows 10 | commands, process control, screenshots |
| Bundled Python 3.12 venv (`dnvenv`) | backend runs/tests; project has no committed venv |
| Node.js 24 + pnpm 11 (bundled paths) | frontend install/typecheck/build; **no npm in bundle** |
| Next.js 16 / React 19 / TypeScript | frontend |
| pytest 9 | 41 backend test files, 739 tests |
| Playwright 1.64 + Chromium | browser QA against local and live builds |
| httpx / requests | API probes and deployment tests |
| PythonAnywhere API | file upload, static upload, reload; token in private folder |
| Docker Compose | intended local deployment; **unusable in this dev sandbox** due WSL/named-pipe denial |
| Supabase | auth, PostgreSQL snapshots/RPC, storage |
| Google OAuth | sign-in |
| ReportLab / openpyxl | PDF and Excel exports |
| phonenumbers, scikit-learn, pandas | cleaning engine |
| Office.js + Office Add-in manifest tooling | Excel add-in; `office-addin-manifest` validation, `office-addin-dev-settings` sideload |
| `cryptography` + `certutil` | localhost certificate generation/trust |
| Excel COM automation + UI Automation + screen capture | end-to-end Excel verification on this machine |
| Git + GitHub | version control; credential-manager auth for `arsanyarsanious` |
| System.Drawing / PowerShell | icon generation, screenshots |

Known environment quirks:

- Docker cannot run in this sandbox; native uvicorn is used.
- The bundled Node has no npm; use pnpm via the bundled path.
- The project has Python 3.13 on PATH but the backend venv is 3.12; the add-in
  setup prefers 3.12 and falls back. The local `.venv` junction is ignored.
- pytest needs `TMP`/`TEMP`/`STORAGE_DIR`/`PYTHONPATH` set; Windows temp ACL
  errors appear otherwise.
- Playwright needs `NODE_PATH=<project>\frontend\node_modules`.
- PythonAnywhere has a 60s request ceiling and 100MB body cap; outbound requires
  a proxy/whitelist.
- Excel in this test environment is “Unlicensed Product”; this blocks Office.js
  formatting writes until signed in/licensed.

### Key file map

- `backend/app/main.py` — API shell; largest file
- `backend/app/core/workflow.py` — decisions, CAS, replay
- `backend/app/core/interactive.py` — cell annotations/proposals
- `backend/app/core/imputation_readiness.py` — analysis schema 10 / gates
- `backend/app/services/workflow_jobs.py` — background workflow jobs
- `backend/app/services/storage.py` / `cloud_storage.py` — persistence
- `backend/app/services/identity.py` — auth/usage
- `backend/app/services/sharing.py` — share tokens
- `backend/app/services/ai_assist.py` — BYOK assistant
- `backend/app/services/addin.py` — Excel analyzer endpoint
- `frontend/app/workspace/page.tsx` — upload/flow orchestration
- `frontend/components/interactive-sheet.tsx` — sheet/panels/tools/results
- `frontend/components/column-settings.tsx` — types/rules/imputation/AI
- `frontend/app/premium-theme.css` — final design layer
- `frontend/app/layout.tsx` — CSS import order and font
- `excel-addin/taskpane/taskpane.js` — Office.js analyzer/highlighter
- `excel-addin/companion/run.ps1` / `setup.ps1` / `certs.py`
- `excel-addin/manifest.xml` — sideload manifest
- `docs/excel-addin-plan.md` — full add-in roadmap
- `docs/upload-reliability.md` — async analysis/timeout history
- `docs/percentage-scale.md` — Phase A decisions
- `docs/issue-corrections.md` — per-issue menu relevance
- `SECURITY_AUDIT.md` — current security findings, authorization test evidence and remediation order
- `PROJECT_CONTEXT.md` — chronological product history

## 12. Quick reference

| Item | Value |
|---|---|
| Repo | https://github.com/arsanyarsanious/DataNeat |
| Branch/commit | `main` / latest commit (see `git log`) |
| Live | https://arsany.pythonanywhere.com/ |
| Local project | `C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable` |
| Backend venv | `C:\Users\Arsany Arsanious\Documents\deepseek-harness\default-workspace\dnvenv` |
| Backend tests | 739 passed |
| API health (live) | `/api/health` returns status/limits only (no disk fields) |
| Auth guard | `REQUIRE_AUTH=true` in live config; fail-closed if Supabase is missing |
| Excel task pane | `https://localhost:9443/taskpane.html` |
| Excel manifest | `excel-addin/manifest.xml` |
| Add-in test workbook | `C:\Users\Arsany Arsanious\Documents\deepseek-harness\default-workspace\DataNeat-addin-test.xlsx` (not repo) |
| Deployment scripts | `C:\Users\Arsany Arsanious\Documents\deepseek-harness\default-workspace\pa_*.py` |
| Deployment status | `C:\Users\Arsany Arsanious\Documents\Codex\outputs\dataneat-deployment\DEPLOYMENT_STATUS.md` |
| Private secrets | `C:\Users\Arsany Arsanious\Documents\Codex\private\` — never print |

# DataNeat

A working, local spreadsheet cleaning application. Upload real CSV/XLSX files, explore column profiles and quality issues, review a deterministic cleaning plan, preview changes, and export a validated copy. No account, payment, or external AI API is required.

## Run with Docker (Windows, macOS, Linux)

Install Docker Desktop with Compose (use Linux containers on Windows). From this repository:

```sh
# Optional: copy .env.example to .env and adjust settings.
docker compose up --build
```

Open `http://localhost:3000`. Backend OpenAPI documentation is at `http://localhost:8000/docs`. Both published ports bind to loopback by default. Stop with `docker compose down`; add `--volumes` only if you want to delete stored uploads.

The frontend proxies `/api` to the backend; browser requests and session cookies stay on one origin. The backend healthcheck must pass before the frontend starts.

## Native development

Requires Python 3.12+ and Node.js 22+. All commands start in the repository root unless noted.

```sh
python -m venv .venv
# Linux/macOS
.venv/bin/python -m pip install -r backend/requirements.lock.txt
# Windows PowerShell equivalent
# .venv\Scripts\python -m pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
```

Start the backend in one terminal:

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
# Windows: .venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Start the frontend in another terminal:

```sh
npm run dev --prefix frontend
```

Open `http://localhost:3000`. Python and npm lockfiles reproduce the validated dependency set. Backend storage defaults to `storage/` relative to the backend process's working directory. Native processes do not automatically read `.env`; set variables in your terminal when overriding defaults. Docker Compose consumes `.env`.

## Workflow

1. Choose or drop a CSV/XLSX file. Excel files expose a worksheet selector; changing worksheets reimports from the selected original file.
2. Explore paginated original data and column profiles. Inspect missing counts, duplicates, type match scores, capitalization conflicts, and date evidence.
3. Review the cleaning plan. Whitespace trimming is the only initially enabled operation. Missing-marker normalization, capitalization, numeric/boolean/date normalization, and row removal require selection. You can configure markers, capitalization, duplicate keys, date interpretation, and approved renames.
4. Preview the approved transformations, then apply them. The backend runs a bounded background job on a separate DataFrame copy.
5. Read the validation report and unresolved issues. Download CSV, XLSX, or a JSON cleaning report. Revising a plan always starts from the preserved original, rather than stacking transformations accidentally.
6. Delete the upload and its jobs when done, or allow expiry after 24 hours.

`sample_data/messy_customers.csv` and `sample_data/messy_workbook.xlsx` are real test inputs. No analysis results are hardcoded into the UI.

### Resolving date and currency issues

Analysis now lists issues alphabetically under prominent column names; columns with no issues are collapsed separately. The cleaning plan uses the same column grouping, and results group unresolved issues by column.

Date-shaped values such as `88-99-2089` are recognized as invalid even when the column contains no valid dates. Under **Resolve Invalid Dates**, explicitly enable the operation, then choose either **Replace all invalid dates with empty cells** or **Correct individual rows manually**. Manual controls show the original invalid value and spreadsheet row number (including the header); enter a valid `YYYY-MM-DD` date or select that row's empty-cell checkbox. Paging does not discard your selected corrections. Unedited rows and valid/ambiguous dates are preserved by this operation.

Mixed currency notation (`$100`, `200 USD`, `300`) is flagged with counts for each representation. The simple add/remove/no-change choices are described below. For currency-aware handling, select **Advanced currency-aware formatting** under **Normalize Currency**, then choose the intended currency and output notation (code, supported symbol, or numbers only). Explicitly confirm whether bare numbers use that currency, and whether ambiguous symbols such as `$` or `¥` refer to it. Unconfirmed values and other currencies remain unchanged. For example, approving USD, bare amounts, and `$` produces `USD 100`, `USD 200`, and `USD 300`; `EUR 400` stays as `EUR 400`. There is no exchange-rate conversion. Supported ISO codes are listed in the currency selector; unsupported formats remain unchanged.

### Bulk selection and percentage consistency

The review step includes **Select all** and **Deselect all**, with a partial-selection indicator when only some actions are enabled. Selecting all includes row-removal suggestions; the notice identifies them, and operations still run only when you click Apply Cleaning. Existing operation settings are retained, and currency/percentage interpretations remain your choice.

Percentage columns containing both `10%` and bare values are flagged as **Mixed percentage notation**, with counts for each representation. **Normalize Percentage** offers three outputs: include the sign (`10%`), omit it as percentage points (`10`), or omit it as a fractional ratio (`0.1`). Choose how to interpret bare numbers: percentage points (`10` means `10%`), fractional ratios (`0.1` means `10%`), or preserve them unchanged. For example, `10%`, `0.2`, and `30%` become `10%`, `20%`, `30%` when bare values are confirmed as fractional ratios; selecting percentage-point output produces `10`, `20`, `30`. No scale is inferred from value ranges. Missing and invalid values remain unchanged, and the original upload is preserved. Ratios here mean decimal fractions, rather than `1:2` or `1/2` notation.

### Simple notation choices and phone numbers

Percentage, currency, and numeric-unit controls now offer **No change**, **Add to all numbers**, and **Remove from all numbers**. These simple choices preserve the numeric text and scale: `10%`, `20`, `0.2` become `10%`, `20%`, `0.2%` when adding, or `10`, `20`, `0.2` when removing. They do not multiply/divide values. Currency/unit symbols can be placed before or after every recognized numeric value, including bare numbers. Removing strips all labels, including different currencies; adding replaces them with your chosen label. This discards unit/currency information and does not perform conversion, so review the preview. No change preserves the original value exactly. Missing and unsupported values remain unchanged. The earlier currency-aware and percentage-rescaling controls remain available under the advanced options.

Phone columns are recognized from names such as Phone, Mobile, Telephone, and Phone Number, or strong international-number evidence. Analysis flags mixed `+`, `00`, bare country-code, and local formats, and reports recognizable country codes and unsupported phone values. Different countries alone are not treated as a formatting error.

**Normalize Phone** offers: no change; add country codes with `+`; add country codes without `+`; remove country codes and return local numbers; remove `+` only; or add `+` to recognized international numbers. Select the country for local/unprefixed numbers (use a two-letter ISO code for countries outside the dropdown). For Egypt, `+201001234567`, `201001234567`, `00201001234567`, and `01001234567` can all become `+201001234567`, `201001234567`, or local `01001234567` according to your choice. Existing explicit foreign country codes are not overwritten. Local dialing prefixes, including meaningful Italian leading zeros, are handled by offline `phonenumbers` metadata rather than arithmetic or blind prefix removal. Invalid, unresolved, or unsupported extension formats are preserved. This checks formatting/plausibility, not ownership or reachability. There is no external phone lookup.

Exports retain formula-injection protection; CSV/XLSX string values beginning with `+` can carry the text-escape apostrophe. The phone parser recognizes a formula-safe `'+...` value on reimport while leaving it intact in no-change mode. Use the preview and report to review formatting changes before downloading.

### Preservation rules

- CSV values are read without pandas type coercion, including leading zeros, whitespace, and literal missing markers. Encoding and delimiter are detected.
- Excel uses read-only openpyxl parsing. String identifiers and simple numeric zero-padding formats (e.g. `000`) preserve leading zeros. Native Excel dates retain their date/time values.
- Duplicate or empty headers receive unique names and the UI reports the adjustments.
- Type match scores are the fraction of observed values matching a rule, **not calibrated probabilities**. Identifier names and leading zeros take precedence over numeric inference.
- Numeric cleaning uses decimal arithmetic, preserving large integers and decimal precision. Unsupported decimal/grouping conventions stay unchanged. Currency symbols are retained; currencies are never converted or merged. Percentage normalization can retain the sign, emit bare percentage points, or emit fractional ratios after user review.
- Both valid interpretations of `05/10/2025` are recognized. Nonambiguous dates contribute evidence; conflicting evidence is reported. **Ambiguous values remain unchanged unless the user explicitly selects day-first or month-first.** Evidence alone never changes them.
- Invalid values remain available for review. Missing values are not filled or invented. Executed operations do not imply that the data is completely clean.
- Exported string cells and headers beginning with formula-control characters (including after leading whitespace) are prefixed with an apostrophe. This deliberately changes their exported representation for spreadsheet safety. Original stored data is unchanged.

## Architecture and directory structure

```text
backend/
  app/
    main.py                    FastAPI endpoints and background-job orchestration
    core/
      common.py                Missing markers, scalar serialization, decimal parsing
      symbols.py               Literal numeric prefix/suffix labels
      phone.py                 Offline country-code and phone formatting
      percentage.py            Percentage notation and optional explicit scaling
      currency.py              Currency notation and optional currency-aware handling
      profiler.py              Read-only column and dataset profiling
      type_detector.py         Context-aware heuristic semantic types
      issue_detector.py        Missing, whitespace, case, type, duplicate detection
      date_analyzer.py         Structural patterns, validity, ambiguity, evidence
      cleaning_plan.py         Reviewable transformation recommendations
      cleaner.py               Deterministic approved transformations and logs
      validator.py             Reprofile, compare, and report unresolved issues
      file_parser.py           Bounded CSV and XLSX parsing
    models/requests.py         Pydantic cleaning request validation
    services/storage.py        Private persistent uploads, isolation, expiry
    services/limits.py         Streaming request-body limits
  tests/                       pytest engine and API tests
  requirements.txt             Direct dependencies
  requirements.lock.txt        Exact validated dependency set
  Dockerfile
frontend/
  app/                         Next.js App Router, responsive light/dark workflow
  components/data-table.tsx    TanStack paginated spreadsheet view
  components/ui/button.tsx     shadcn/ui Button pattern (Radix Slot + CVA)
  lib/                         Typed API client, models, styling helpers
  tests/                       Playwright browser workflows
  components.json              shadcn/ui configuration
  package-lock.json
  Dockerfile
sample_data/                   Messy CSV and multi-worksheet Excel fixtures
docker-compose.yml
.env.example
pytest.ini
```

React, TypeScript, Tailwind CSS, Lucide, shadcn/ui component conventions, and TanStack Table power the frontend. FastAPI, Pydantic, pandas, and openpyxl power the backend. The core engine is independent of HTTP, and authentication, billing, persistent task queues, or other integrations can be added without replacing it.

### API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Readiness and configured upload limit |
| POST | `/api/files/upload` | Multipart `file`, optional `sheet`; returns profile, preview, plan |
| GET | `/api/files/{file_id}/preview` | `page` and `page_size` (1–100) |
| GET | `/api/files/{file_id}/profile` | Integrated original profile |
| GET | `/api/files/{file_id}/invalid-dates` | Session-authorized, paginated invalid rows for the `column` query parameter |
| GET | `/api/files/{file_id}/issues` | Column issues and duplicate count |
| GET | `/api/files/{file_id}/cleaning-plan` | Suggested operations |
| POST | `/api/files/{file_id}/preview-cleaning` | Preview `{ "operations": [...] }` without saving changes |
| POST | `/api/files/{file_id}/clean` | Submit approved operations; returns `job_id` (202) |
| GET | `/api/jobs/{job_id}` | queued/running/completed/failed status |
| GET | `/api/jobs/{job_id}/results` | Paginated cleaned data, operation logs, validation |
| GET | `/api/jobs/{job_id}/download` | `format=csv`, `xlsx`, or `report` |
| DELETE | `/api/files/{file_id}` | Delete stored upload and all associated jobs |

Operations require `enabled: true` to execute. Supported names: `trim_whitespace`, `normalize_missing_values`, `normalize_capitalization`, `normalize_numeric`, `normalize_boolean`, `normalize_dates`, `resolve_invalid_dates`, `normalize_currency`, `normalize_percentage`, `normalize_symbols`, `normalize_phone`, `remove_duplicates`, `rename_column`. See OpenAPI and the generated cleaning plan for schema and parameters. API scripts must retain the `dataneat_session` cookie; identifiers alone never authorize access.

## Environment variables

All have defaults; no secrets are required.

| Variable | Default | Applies to |
| --- | --- | --- |
| `MAX_UPLOAD_MB` | `20` | Backend; UI obtains the limit from health endpoint |
| `STORAGE_DIR` | `storage` (Compose: `/app/storage`) | Backend; private server-created data only |
| `CORS_ORIGINS` | `http://localhost:3000` | Backend; comma-separated exact browser origins |
| `COOKIE_SECURE` | `false` | Backend; set `true` behind HTTPS |
| `API_INTERNAL_URL` | `http://127.0.0.1:8000` (Docker: `http://backend:8000`) | Next.js proxy, configured at build/start |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | unset | Tests; optional installed Chromium executable |
| `PLAYWRIGHT_BASE_URL` | `http://127.0.0.1:3000` | Tests; optional running frontend origin |

Changing the Docker frontend's internal API URL requires rebuilding so its rewrite configuration matches. The Compose file sets the service URL for both build and runtime.

## Tests and verification

From the root:

```sh
.venv/bin/python -m pytest -q
npm run build --prefix frontend
npm run typecheck --prefix frontend
```

End-to-end tests (auto-start the backend and frontend, or reuse running services):

```sh
cd frontend
npx playwright install chromium
npm run test:e2e
```

On Windows use `.venv\Scripts\python` for pytest. Playwright's backend-start command currently uses the POSIX virtualenv path; on Windows, start the backend and frontend manually before running the browser suite, which will reuse them.

Where Chromium is already installed, you can avoid browser downloads:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e
```

The suite verifies real CSV upload, profiling, plan approval, before/after preview, duplicate removal, ambiguous-date preservation, safe downloadable output, deletion, mobile layout, dark mode, Excel worksheet switching, explicit date interpretation, and XLSX download. Backend tests verify all engine components, CSV encodings/delimiters, unique headers, Excel identifiers, authorization isolation, expiry, upload limits, rate limits, numeric precision, and formula-safe CSV/XLSX exports.

Validation results from this implementation are recorded in `VALIDATION.md`.

### Corporate/cloud proxy builds

Docker builds normally use system trust. Both Dockerfiles also accept an optional BuildKit secret named `build_ca` containing a trusted CA bundle. A Compose build override may supply that secret and proxy build arguments (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`) on managed networks. The bundle is mounted only during dependency installation and is not included in the image. Never disable certificate verification to work around a proxy.

## Security, privacy, and limits

- Unpredictable UUID file/job IDs and a separate HttpOnly, SameSite session cookie isolate uploads and downloads. No third-party AI or training pipeline receives data.
- Storage paths derive only from validated UUIDs; user filenames never become disk paths. Storage directories/files use restrictive permissions; original bytes and parsed values are server-created serialized records.
- Uploads are limited to CSV/XLSX, 20 MB by default, 100,000 rows, and 200 columns. XLSX expanded ZIP content is limited to 100 MB. Streaming request limits also cover chunked uploads.
- Previews contain at most 100 rows per request. The cleaning executor has two workers, at most eight queued/running jobs, and at most 100 retained jobs. Storage accepts at most 100 retained uploads.
- Basic rate limiting allows 120 requests/minute per observed client IP. CORS is explicit and mutation requests reject unexpected browser origins.
- Expiry is checked on every read; a background task physically removes expired uploads/jobs approximately every minute while the server is running. Expired data left while offline is purged on the next startup. Manual deletion removes associated job results.
- Spreadsheet contents are not logged. Error messages avoid exposing uploaded contents; deployment access logs can still contain file/job IDs. JSON reports intentionally include issue examples and should be treated as confidential.

### Known limitations before public deployment

This is a local, single-instance MVP, not a hardened multi-tenant public service. There is no user authentication, billing, encryption at rest, persistent job queue, or distributed rate limiter. Jobs/results are in memory and disappear on backend restart; original uploads persist until deletion/expiry. Sessions are browser-cookie based, so losing the cookie loses access to the corresponding files. The UI workspace state is not restored after a page reload.

Run exactly one backend worker. Scaling to multiple processes requires shared job/session storage and a durable queue. Behind the Next.js proxy the backend sees the proxy's IP, so its basic rate limiter may be shared across users; add a trusted gateway rate limiter before public exposure. Add HTTPS, authentication, tenant quotas, encrypted durable storage, restrictive infrastructure access, monitoring, and disk/memory budgets before accepting confidential data from public users.

Parsing, profiling, previews of cleaning, and validation are bounded but operate in memory. Expensive cleaning runs in the background; initial upload analysis awaits a threadpool result. Near-limit or highly irregular spreadsheets can still need substantial memory. There is no large-file benchmarking claim.

Only the selected worksheet is exported. Workbook styles, merged cells, charts, macros, formula evaluation, and arbitrary Excel display formats are not preserved. Formulas are treated as untrusted text and escaped on export. Date support is intentionally limited to the documented formats, ISO datetimes, and English month names. Ambiguous date confirmation applies to the entire selected column; inspect mixed-origin columns before approving it. Unsupported numeric locales remain unchanged; supported ISO currency codes and symbols can be standardized after explicit approval, but there is no currency conversion, and missing-value imputation is available only after explicit review and approval. Type detection is heuristic, and unmatched or unusual formats may need manual correction outside this MVP.

## Recommended next improvements

1. Durable jobs and resumable browser workspaces, followed by authentication and tenant isolation.
2. Per-cell date resolution and explicit locale-specific numeric/date formats.
3. Encrypted object storage, quotas, gateway limits, and operational monitoring for public hosting.
4. File-size/concurrency benchmarks, chunked processing, and broader Unicode/date/Excel-format fixtures.

Analysis display options let you sort issue columns by name (A–Z), original spreadsheet position (left to right), or reverse position. Healthy columns remain in their separate expandable section and follow the same ordering. These display options do not reorder exported data.

For currency columns, choose **Add the chosen symbol to all numbers** or **Remove all symbols / labels**, then choose whether to include thousands-separator commas. All recognized amounts receive the selected format; decimal digits are retained without rounding or currency conversion. **No change** preserves the original values. Missing and unsupported values remain unchanged. The in-app privacy policy explains processing location, session access, deletion, retention, and the absence of third-party data sharing or AI services in the current application.


## Missing-data imputation

DataNeat offers opt-in **mean, median, mode, constant, forward fill, backward fill, and linear interpolation**, plus **group mean, group median, group mode, group forward fill, and group backward fill**. No imputation is selected or applied automatically. KNN and regression are not implemented; the current feature does not introduce external AI services, predictive features, or scikit-learn dependencies.

### Review workflow

1. Upload a spreadsheet (try `sample_data/missing_measurements.csv`) and open **Review cleaning plan**.
2. Each column with missing cells has an **Imputation** action with its type, missing count/percentage, distribution evidence, available methods, and a suggested method. Numeric suggestions use skewness and IQR outlier evidence; categorical suggestions use observed frequencies. Repeated labels and ordering columns yield conditional grouping/time-series suggestions. These are assumptions to review, not evidence that missingness is random.
3. Enable only the imputation actions you want and choose a method. For a constant, enter a non-missing value; `0` is allowed when it actually means zero. Identifiers are excluded from arithmetic methods. Mode ties use the first observed value deterministically.
4. Select entity grouping columns for grouped or sequential data. Ordered methods require an explicit ordering column; without grouping, explicitly confirm that all rows form one related sequence. For the example file, select `Entity` and order by `Time`.
5. Approve any necessary marker normalization, type/date conversion, and formatting actions. With active imputation, the engine runs approved marker normalization first, then whitespace and type/date conversions, formatting, imputation, duplicate removal, and renaming. It validates dependencies against the resulting data, independently of submitted action order. Refer to original column names when imputation is active, since renaming runs last. Plans without active imputation retain their existing execution order. Custom missing markers must be explicitly normalized before they can be imputed.
6. Click **Preview changes**. Highlighted cells are estimates; the imputation audit reports actual filled cells, remaining missing values, method, grouping/ordering, warnings, and before/after numeric statistics and category frequencies. Other cleaning actions may also change observed cells if separately approved; imputation itself never overwrites non-missing cells.
7. Confirm each selected column after reviewing its preview, then **Apply cleaning**. Any configuration/action change invalidates the preview and confirmations. Selecting all cleaning actions does not approve estimates. The clean API also requires explicit imputation confirmation.
8. Download CSV/XLSX and the JSON report. Exported data retains its column layout; the report includes original `row_index`, `spreadsheet_row` (header is row 1), and `is_imputed: true` per filled cell. Preview highlighting follows retained original row identities through pagination, duplicate removal, and renaming.

### Safeguards and limits

- Numeric methods require every observed target value to be a finite plain number and the target to be a numeric measurement. Unsupported mixed values, ambiguous currency/percentage units, booleans, and identifiers block arithmetic rather than being silently coerced. Review safe conversions first. Arbitrary numeric locales are not supported.
- Ordering must be complete and unique within each group and use finite numeric coordinates or valid ISO dates/timestamps. Ambiguous or invalid date ordering blocks the operation until safely corrected/converted. Interpolation uses actual numeric/time spacing, not row positions, and requires at least two observations.
- Calculations sort temporarily in ascending coordinate order; original spreadsheet order is preserved. Directional fill and interpolation fill interior gaps only: no leading/trailing extrapolation is supported. No sequence fill crosses group boundaries. Missing group keys and groups without sufficient observations remain missing, with warnings.
- An entirely missing column has no data-driven estimate; the UI offers a user-defined constant or no change. Statistical methods invoked through the API leave groups/columns without observations unfilled. Empty frames are handled safely.
- Mean imputation can reduce variance and distort correlations; median/mode can distort distributions. Directional fills assume continuity within related entities; backward fill can leak future information. These estimates are not verified facts and should not replace domain judgment. No predictive/model-based methods are available in this implementation.
- A validation failure blocks the operation with a column-specific explanation. Preview errors return HTTP 422; jobs that fail expose the explanation in job status. No partial cleaned export is published, and the original upload remains intact.
- Counts/distribution audits describe each imputation operation before any later approved duplicate removal. The cell flags in the preview identify only retained rows. Frequency samples show the ten most frequent observed values; cross-column missing-pattern reports show up to twenty patterns.

### Imputation API

Use the existing session-scoped endpoints; no additional upload or job flow is required:

```json
{
  "operations": [
    {
      "id": "impute-reading",
      "column": "Reading",
      "operation": "impute_missing_values",
      "enabled": true,
      "parameters": {
        "method": "linear_interpolation",
        "group_by": ["Entity"],
        "order_by": "Time",
        "single_entity": false,
        "confirmed": false
      }
    }
  ]
}
```

Send this body to `POST /api/files/{file_id}/preview-cleaning`. After reviewing the response, set `confirmed: true` and send it to `POST /api/files/{file_id}/clean`. For statistical/group methods omit `order_by`; for `constant` provide `value`. `group_by` accepts up to five distinct columns; ordered methods require grouping or `single_entity: true`. Supported method identifiers are `preserve`, `mean`, `median`, `mode`, `constant`, `forward_fill`, `backward_fill`, `linear_interpolation`, `group_mean`, `group_median`, `group_mode`, `group_forward_fill`, and `group_backward_fill`.

Profiles now include per-column `statistics`, `missing_pattern`, and (for columns with gaps) `imputation` recommendations; dataset profiles include `missing_patterns`. Preview/result tables include an aligned boolean `is_imputed` matrix. Operation logs and downloadable reports include `method`, `missing_before`, `missing_after`, `imputed_count`, `imputed_cells`, `group_by`, `order_by`, `warnings`, `failures`, `distribution_before`, and `distribution_after`. Validation exposes total `imputed_cells` and the per-operation `imputation` audit. `GET /api/jobs/{job_id}/results` and download endpoints retain existing session access checks.

Mean/median choices are also shown for currency/unit columns and salary-like numeric columns that were inferred as text. These are conditional options: first approve removal of currency/unit labels (or a confirmed currency-aware numbers-only format) and normalization of any unsupported placeholders. Arithmetic still refuses unresolved text, incompatible units, or protected identifiers. Existing amounts are never silently ignored when calculating an estimate.

## Interactive spreadsheet cleaning

Choose **Interactive spreadsheet: basic cleanup first** before uploading, or click **Open interactive spreadsheet** from the analysis page. This is an additional workflow; the existing cleaning-plan and advanced imputation controls remain available.

Opening this mode creates a separate editor copy. Its basic pass trims whitespace, standardizes suitable text capitalization (preserving short observed acronyms), converts recognized boolean/numeric notation, and formats unambiguous dates as ISO dates. Identifier/phone/currency/percentage notation, ambiguous dates, invalid values, emails, and free-text notes are not guessed or automatically relabeled. The basic cleanup report lists the changes. The original uploaded frame and bytes are preserved.

Remaining supported issues are colored by category: missing values, invalid/ambiguous dates, capitalization, whitespace, currency/percentage/unit notation, phone formats, type mismatches, email syntax, and duplicate rows. Multiple issues on one cell have multiple color markers; a legend and descriptions make the meaning independent of color. Currency/percentage inconsistency is a column-wide issue and may remain highlighted until all relevant values use a consistent notation. Email checks validate syntax, not mailbox delivery.

Hover over a highlighted cell, click it, or focus it with the keyboard to open its nearby action panel (on mobile, tap to open a bottom panel). Select a manual correction/clear, date interpretation, case/notation/phone fix, or a missing-value estimate. Choose **This cell** or **This column** where applicable, click **Preview fix**, review before/after examples and warnings, and click **Confirm and apply**. **Cancel**, **Close**, or Escape leaves the editor copy unchanged. Changing an option invalidates its proposal. The server checks the sheet revision to reject stale changes.

After confirmation, the sheet is profiled again and cell colors are updated. Clearing an invalid date resolves its date error but creates a missing-value issue; filling missing cells requires an explicit estimate or a supplied value. Mean/median require safe plain numeric amounts; normalize currency labels first when appropriate. Grouping can be selected for editor mode/mean/median estimates. Directional/model/advanced imputation continues through the existing cleaning-plan workflow. Duplicate removal is a dataset action, requires preview/confirmation, and keeps original row identities for the remaining rows.

Download the editor copy as **XLSX** or **CSV**, and download the **REPORT** for basic-cleanup and confirmed-action logs. Exports retain the existing spreadsheet-formula escaping safeguards. Files and editor state are session-scoped and follow the existing expiry/deletion rules; use Delete file to remove both original and editor copy. This is a paginated web spreadsheet preview, not an embedded native Excel application; only the selected worksheet is exported, and existing workbook-style/macro limitations apply. Automatic detection remains heuristic and cannot guarantee that every real-world semantic error is discoverable.

### Interactive API

- `POST /api/files/{file_id}/editor/start`: initialize the cleaned copy once (subsequent calls resume it).
- `GET /api/files/{file_id}/editor?page=1&page_size=25`: sheet preview, original `row_indices`, aligned `cell_issues`, current profile/revision, and audit logs. Page size is limited to 100.
- `POST /api/files/{file_id}/editor/fix`: submit `revision`, `column`, `row_index`, `scope` (`cell`/`column`), `action`, `parameters`, optional manual `value`, and `confirmed` (false for preview, true to apply). A preview returns modified counts, up to ten before/after examples, and warnings. Invalid requests return 422; a stale revision returns 409. Manual replacement is cell-only. Row duplication removal applies to the dataset.
- `GET /api/files/{file_id}/editor/download?format=xlsx|csv|report`: export the current editor copy or JSON audit report.

All endpoints use the existing private session checks. Neither starting the editor nor applying a cell fix changes the original uploaded data or the independent cleaning-plan results.

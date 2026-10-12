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

Mixed currency notation (`$100`, `200 USD`, `300`) is flagged with counts for each representation. Under **Normalize Currency**, choose the intended currency and output notation (code, supported symbol, or numbers only). Explicitly confirm whether bare numbers use that currency, and whether ambiguous symbols such as `$` or `¥` refer to it. Unconfirmed values and other currencies remain unchanged. For example, approving USD, bare amounts, and `$` produces `USD 100`, `USD 200`, and `USD 300`; `EUR 400` stays as `EUR 400`. There is no exchange-rate conversion. Supported ISO codes are listed in the currency selector; unsupported formats remain unchanged.

### Preservation rules

- CSV values are read without pandas type coercion, including leading zeros, whitespace, and literal missing markers. Encoding and delimiter are detected.
- Excel uses read-only openpyxl parsing. String identifiers and simple numeric zero-padding formats (e.g. `000`) preserve leading zeros. Native Excel dates retain their date/time values.
- Duplicate or empty headers receive unique names and the UI reports the adjustments.
- Type match scores are the fraction of observed values matching a rule, **not calibrated probabilities**. Identifier names and leading zeros take precedence over numeric inference.
- Numeric cleaning uses decimal arithmetic, preserving large integers and decimal precision. Unsupported decimal/grouping conventions stay unchanged. Currency symbols are retained; currencies are never converted or merged. Percentage labels remain percentages.
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

Operations require `enabled: true` to execute. Supported names: `trim_whitespace`, `normalize_missing_values`, `normalize_capitalization`, `normalize_numeric`, `normalize_boolean`, `normalize_dates`, `resolve_invalid_dates`, `normalize_currency`, `remove_duplicates`, `rename_column`. See OpenAPI and the generated cleaning plan for schema and parameters. API scripts must retain the `dataneat_session` cookie; identifiers alone never authorize access.

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

Only the selected worksheet is exported. Workbook styles, merged cells, charts, macros, formula evaluation, and arbitrary Excel display formats are not preserved. Formulas are treated as untrusted text and escaped on export. Date support is intentionally limited to the documented formats, ISO datetimes, and English month names. Ambiguous date confirmation applies to the entire selected column; inspect mixed-origin columns before approving it. Unsupported numeric locales remain unchanged; supported ISO currency codes and symbols can be standardized after explicit approval, but there is no currency conversion or automatic missing-value imputation. Type detection is heuristic, and unmatched or unusual formats may need manual correction outside this MVP.

## Recommended next improvements

1. Durable jobs and resumable browser workspaces, followed by authentication and tenant isolation.
2. Per-cell date resolution and explicit locale-specific numeric/date formats.
3. Encrypted object storage, quotas, gateway limits, and operational monitoring for public hosting.
4. File-size/concurrency benchmarks, chunked processing, and broader Unicode/date/Excel-format fixtures.

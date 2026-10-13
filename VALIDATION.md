# Validation record

Validated on 2026-10-11 in the attached Linux cloud workspace.

| Check | Result |
| --- | --- |
| Backend `python -m pytest -q` | **34 passed**, no failures or skipped tests |
| Frontend `npm run build` | Production build passed |
| Frontend `npm run typecheck` | Passed |
| Playwright development workflows | **3 passed** before the final reporting/parameter-validation refinements |
| Playwright against final Docker production stack | **3 passed**, no failures or skipped tests |
| Backend Docker image | Built and started as the unprivileged `dataneat` user; healthcheck passed |
| Frontend Docker image | Production Next.js server started; backend proxy functional |
| Proxied `/api/health` | Returned `status: ok`, upload limit 20 MB |
| npm dependency audit | No known vulnerabilities reported |
| pip-audit of every pinned Python dependency | No known vulnerabilities reported |
| Reusable install script | Executed successfully: virtualenv setup, frozen Python/npm installs, pytest, production build |
| Source whitespace check | Passed |

The final browser suite exercised real CSV upload and profiling, approval and before/after preview, duplicate removal, preservation of `05/10/2025`, validation, formula-safe CSV download, manual deletion, mobile dark mode, upload errors, Excel worksheet selection, explicit month-first interpretation, and XLSX download. Downloads were received by the browser, and the CSV contents were checked for identifiers, preserved ambiguous values, and escaped formulas. Backend tests additionally inspected XLSX cells, cross-session authorization, original-value preservation, invalid operation parameters, numeric precision, row pagination, expiry/deletion, rate limiting, request/file limits, zero-padded Excel identifiers, and UTF-16/Unicode CSV parsing.

One backend test-run warning remains: Starlette 1.7 deprecates its httpx-backed TestClient in favor of httpx2. Tests executed and passed using the supported compatibility path; no assertions were disabled. Browser runs report a harmless NO_COLOR/FORCE_COLOR tooling warning. Earlier test selector and development-origin problems were corrected before final verification.

Docker's build network in this cloud environment needed a temporary build-only override for host networking, proxy DNS, proxy build arguments, and the provided system CA bundle. The CA was supplied through the Dockerfiles' optional `build_ca` secret. TLS verification remained enabled. Neither proxy configuration nor the environment-specific CA bundle was committed into the project or baked into the images. Standard Compose configuration was validated, and the final application runs with the normal Compose service network.

Both production containers were left running on loopback ports 3000 and 8000. Test uploads were deleted by the successful browser workflows. Live processes and in-memory job results are not assumed to survive cloud publication or a server restart.

Cloud configuration draft persistence was confirmed for `install_script` and `start_skill`. These are reusable instructions; saving them did not publish a snapshot. Review and save the draft in environment settings, then publish through the product when ready.

Windows Docker execution and large-file/load benchmarking were **not run** here. Windows-compatible Docker Desktop instructions, native PowerShell equivalents, and public-deployment limitations are documented in README.md. Native browser tests on Windows require manually starting the servers because the Playwright auto-start command uses the POSIX virtualenv path. This record does not claim public production hardening or validation in a fresh cloud task.

## Date, currency, and column-analysis fixes — 2026-10-12

Regression tests now cover columns consisting entirely of impossible dates, explicit clearing and per-row correction, authorization/pagination of invalid date rows, preservation of valid/ambiguous dates and the original upload, ISO currency codes before/after numbers, mixed labeled/bare amounts, explicit symbol and bare-amount assumptions, and preservation of other currencies and identifiers. The analysis, cleaning plan, and unresolved results are grouped by column.

Backend regression suite: **42 passed**. Updated browser suite: **5 passed** in development, including both new correction workflows and downloadable output. The first-session bootstrap race uncovered by fast upload tests was also corrected. Final production verification: **5 browser tests passed** against `next start` and the updated FastAPI backend, including a mobile layout check for the new correction controls and a test ensuring currency changes reset explicit bare-amount confirmations. The production build and TypeScript checks passed. Original uploads, other currencies, and unresolved ambiguous dates remained preserved. Docker configuration and dependencies were unchanged; these fixes were validated with the native production servers rather than a new Docker image build.

## Bulk selection and percentage normalization — 2026-10-12

Backend suite: **49 passed**. Production browser suite: **7 passed**, including Select all/Deselect all, the mixed-selection indicator, inclusion of duplicate-removal suggestions in bulk selection, mixed `%` detection, explicit ratio interpretation, include/omit-sign previews, cleaned CSV download, and preservation of the original upload. Backend regressions cover decimal precision, missing/invalid values, identifier exclusion, semantic ratio hints, and rejected invalid parameters. Production build, TypeScript, and source checks passed. No dependencies or Docker configuration changed; verification used the native production servers.

## Literal notation and phone formatting — 2026-10-13

Backend suite: **61 passed**, including full-column add/remove/no-change behavior, unchanged numeric scale, zero-padded numeric text, arbitrary short unit labels, phone detection and mixed prefix reports, international and national formatting, meaningful leading zeros, preservation of explicit foreign country codes, Italian local numbers beginning with 39, formula-safe phone reimport, invalid parameters, and original-upload preservation. `phonenumbers==9.0.41` is pinned in both dependency files and works offline; the frozen Python install succeeded. The updated browser suite has **8 workflows** covering the simple controls, advanced-mode compatibility, preview, country selection, all-row prefix consistency, CSV downloads, and existing regression workflows. Final production run: **all 8 browser workflows passed** against `next start` and the updated backend. Production build, TypeScript, source checks, and proxied API health passed. These fixes were verified with native production servers; Docker images were not rebuilt during this turn. The existing Docker installation uses the updated frozen dependency file.

### Analysis display, privacy, and uniform currency formatting — 2026-10-13

- Backend: 62 tests passed, including consistent symbol/comma formatting and detection of mixed comma notation.
- Production Next.js build and TypeScript check passed.
- Browser: all 9 Playwright workflows passed against native production servers; the new workflow checks original/reverse/alphabetical analysis order, the privacy section, and both formatted currency rows in the preview.
- Both direct backend and frontend-proxied health requests returned OK. Docker images were not rebuilt for this change.
- The first browser run rejected uploads because the manually restarted backend lacked the test origin in CORS_ORIGINS. Restoring the documented localhost and 127.0.0.1 origins resolved this configuration issue; the complete rerun passed.

### Opt-in missing-data imputation — 2026-10-13

- Implemented seven basic methods and five grouped methods with deterministic mode ties, finite numeric validation, explicit ordering, entity boundaries, missing-key safeguards, and no boundary extrapolation.
- Backend: 123 pytest tests passed, including all methods, empty/all-missing columns, mixed types, unsorted numeric/time sequences, leading/trailing gaps, invalid parameters and dependencies, original/non-missing preservation, deterministic results, explicit approval, API preview/results, CSV/XLSX/report export, provenance through renaming and duplicate removal, and compatibility with existing execution order when no imputation is active.
- Frontend: production Next.js build and TypeScript check passed. All 11 Playwright workflows passed against native production servers, including per-column selection/preview/approval, confirmation invalidation after edits, validation/download, and group/order dependency controls. Existing upload, dates, currencies, percentages, symbols, phone normalization, select-all, privacy, and analysis sorting workflows continue passing.
- Ruff F/I checks and Git whitespace checks passed. Backend health on port 8000 and frontend-proxied health on port 3000 returned OK.
- A test locator was corrected to distinguish the application error alert from Next.js's route announcer. Rapid repeated suites hit the unchanged 120-request/minute limit; a fresh backend run passed the entire browser suite. No rate-limit safeguards were disabled.
- KNN/regression remain optional future work; no scikit-learn or external service was added. Directional fills/interpolation intentionally leave leading/trailing gaps, missing group keys, and insufficient-observation groups unfilled. Docker images were not rebuilt for this feature; native production behavior was validated.

### Salary arithmetic choices — 2026-10-13

- Numeric imputation choices are now exposed for currency/unit and salary-like text columns, with explicit conversion/marker warnings. Identifiers, phones, booleans, and date targets remain protected. Runtime parsing still rejects unresolved labels or unsupported values.
- 125 backend tests and all 12 production browser workflows passed, including currency Salary mean/median visibility and a mean preview after approved symbol removal. TypeScript and Ruff F/I checks passed. This change affects backend recommendation/validation logic; frontend application source and dependencies did not change.

### Readable typography — 2026-10-13

- Main text increased to 16 px, supporting text to 14–15 px, and smaller subheadings to 17 px at the default browser font setting. Small typography now uses relative rem sizes through shared CSS variables, including mobile rules, tables, controls, badges, help text, and imputation labels.
- Production build (including TypeScript checks) and all 12 existing browser workflows passed. The initial mobile check identified a currency-control minimum-width overflow; flexible/grid container sizing was corrected without hiding overflow.
- Manual browser inspection confirmed a 390 px page width on a 390 px viewport with both the default 16 px font setting and a larger 20 px browser default. Desktop and mobile screenshots were inspected. Table content scrolls within its panel.
- This change is CSS only; no backend, dependencies, or calculation behavior changed. Docker images were not rebuilt in cloud.

### Interactive spreadsheet option — 2026-10-13

- Added a separately initialized editor copy with conservative basic whitespace/case/boolean/numeric/date cleanup; original data and classic cleaning-plan results are preserved.
- Colored cell annotations cover supported residual missing, whitespace, date ambiguity/invalidity, case, currency/percentage/unit, phone, type, email-syntax, and duplicate issues. Hover/click/focus panels offer scoped fixes, before/after previews, explicit confirmation, cancellation, and revision conflict protection. Export supports formula-safe CSV/XLSX and a JSON audit report.
- Backend: all 132 pytest tests passed, including native Excel upload/editor initialization, basic-cleanup safeguards, original/session isolation, preview immutability, confirmation, stale revisions, exports, column currency changes, cell imputation, duplicate removal, pagination after row removal, date interpretation, and newly introduced whitespace issues.
- Frontend: production build/TypeScript checks and all 13 Playwright workflows passed. The new workflow covers upload-mode selection, basic cleanup, hover annotations, preview without mutation, confirmed correction, canceled correction, mobile layout, and download. An initial locator was corrected to account for accessible issue-button names inside cells; assertions now check the actual cell text before confirmation.
- Desktop dark-mode and mobile panel screenshots were inspected. Mobile document width equals its 390 px viewport. Backend and frontend-proxied health requests returned OK. Ruff F/I and Git whitespace checks passed.
- Docker images were not rebuilt in cloud. This is a paginated data preview rather than native Excel embedding; existing selected-worksheet/style/macro limitations remain. Advanced sequence/model imputation uses the existing cleaning-plan interface; editor estimates currently offer mode/mean/median with optional grouping.

### Cloudflare deployment preparation — 2026-10-13

- Added opt-in static export, Cloudflare Worker asset serving and a streaming same-origin API gateway. Normal Next.js API rewrites remain enabled outside export mode. Generated assets, Wrangler state, and local variable files are ignored.
- Cloudflare static export and normal production build/TypeScript checks passed. Wrangler 4.11.1 deployment dry-run passed. Three gateway tests passed (assets/missing backend, request body/session and response cookies, origin protection/upstream failures).
- The exported frontend rendered successfully in a browser under local Miniflare. An unconnected backend returned the intentional HTTP 503 explanation. Wrangler could not obtain remote Request.cf metadata under the restricted policy, but local simulation started and served the tested assets correctly.
- Native production upload and interactive-editor smoke checks passed after restoring the normal build; no backend functionality was changed.
- Cloudflare account credentials and a hosted Python backend are not connected, so no Cloudflare publication or public URL is claimed. A secure CLOUDFLARE_API_TOKEN requirement was saved for api.cloudflare.com; it remains a pending configuration change requiring credential entry and publication.

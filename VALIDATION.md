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

## Enhanced workflows — 16 October 2026

- Backend: 195 regression tests passed (two dependency/test deprecation warnings).
- Frontend: production build and TypeScript passed.
- New cases: configurable missing markers, Unicode text, outer/internal whitespace separation, identifier protection, rules and ignored-finding reversal, per-cell audit, recipe mapping on new files, recalculated mean imputation, missing-column failures, cancellation, stale commits, session isolation, dependent-step undo conflicts, Advanced result persistence, background exports and parent-file deletion access checks.
- XLSX boundaries verified with two sheets, a zero-padded ID, formula text, native date and formatting. Export retains the selected data table; it does not preserve the whole workbook or execute formulas.
- Synthetic browser checks: preparation with City NA preserved, currency rules, reviewed Cairo/Kairo suggestion, three-step recipe export, compatible/incompatible batch preview/application, searchable before/after review, PDF and ZIP downloads, workspace refresh.
- Generated PDF inspected visually on all three pages. ZIP contents verified: report.pdf, recipe.json, README.txt, opt-in changes.json.
- Windows launcher parses and readiness-only mode succeeds. Clean-machine installation and cold Docker startup were not simulated.
- Tests do not establish real-world precision/recall or end-user usability superiority. No external service, mandatory account, paid plan or public deployment was introduced.

## Performance follow-up — 17 October 2026

- 197 backend tests pass, including incremental/full-profile equivalence, cross-column duplicate updates and lightweight owner/expiry checks.
- Replaced row-Series construction with tuple iteration, removed repeated per-cell DataFrame lookups and per-value marker normalization, and use sets for rule-row membership.
- Reprofile only dirty columns while reusing unaffected profiles; refresh dataset-wide duplicate annotations on all affected rows.
- Avoid redundant copies of isolated snapshots, redundant init writes and cache-only full-record writes. Preview calculation no longer holds the global storage lock.
- Job polling validates cached owner/expiry metadata instead of loading the entire dataset each poll; early polling is faster with backoff for long jobs.
- Synthetic 5,000-row / five-column benchmark: boolean normalization plus incremental recheck took about 0.33 seconds in the measured run. This excludes initial analysis, disk/HTTP and browser rendering; it is not a guarantee for all datasets.

## Eight-part interface refresh — 21 October 2026

- Implemented all eight approved visual changes: grouped workbook ribbon; wider sheet canvas with smaller desktop sidebar/gutters; separated charcoal workspace/sheet/panel surfaces; opaque muted column headings with a green active-column accent; alternating row shading that preserves issue highlights; consistent correction panel with before/after cards and fixed Apply footer; three export cards; fixed-position cover sample with text/color correction animation.
- Preserved the Begin cleaning → login → workspace order, public theme switch, reduced-motion preference, 48px virtual row height, and existing cleaning handlers. No backend or package dependencies changed.
- Production frontend build and TypeScript passed; rebuilt and restarted the local frontend. Frontend and backend health endpoints responded successfully.
- Browser verification passed in light/dark and 390px mobile viewports: stationary cover geometry, theme/login flow, four ribbon groups, row stripes, selected opaque heading, correction application, history/undo, whole-file search, stable sheet position/size after correction, no mobile document overflow, and no browser errors.
- Downloaded real CSV, XLSX, and PDF exports from the new cards; checked CSV correction contents and XLSX/PDF file signatures. Date-pattern imputation/undo and prominent blocking-error regression checks also passed.
- Inspected cover, sheet, correction, export, and mobile screenshots. Evidence/scripts are under Documents/Codex/outputs/dataneat-ui-review (design-* plus review.cjs, error-review.cjs, pattern-review.cjs).

## Date interpretation confirmation and imputation menus — 21 October 2026

- Fixed a disabled Apply case when Day First + DD/MM/YYYY confirms ambiguous dates without changing their displayed strings. Preview/apply/audit now report interpreted_dates separately; the UI permits these confirmations and explains genuine no-ops beside Apply. Confirmed interpretation is retained for later conversions and date median imputation, and undo restores ambiguity.
- Mean, Median and Mode each appear once in quick/custom correction menus and Column Settings. Optional Group by selects grouped behavior. Stored group_mean/group_median/group_mode recipes remain compatible; directional grouped fills remain available.
- Rebuilt/deployed the final frontend; backend date fix deployed. Full backend suite: 411 passed (two existing deprecation warnings). Focused browser checks passed for interpretation-only Apply, preserved display, undo, deduplicated menus, whole-column mean and grouped median.
- The missing-label and History drawer cards now have safe internal padding, compact text and wrapping for expanded long column names. Four-width browser checks passed, with light/dark screenshots and working per-step undo.
- Sidebar/logo images (Minimal, Studio, Compact, plus dark Compact) were initially shown as proposals. The later Compact selection is implemented below.

## Selected Compact logo and sidebar — 21 October 2026

- Replaced DataNeat's generic mark with the selected three-cell check mark as a crisp SVG component. Brand marks are consistent on the cover, login, workspace sidebar and small workspace footer mark.
- Applied only scoped sidebar styling: restrained light/charcoal surfaces, compact navigation, thin table/privacy icons, green active state, quieter wordmark, footer identity/theme controls and collapse chevrons. Existing routes, handlers, expanded/collapsed widths and spreadsheet styles remain intact. No backend or dependency changes.
- Frontend production build/TypeScript passed and local frontend redeployed. Browser checks passed for logo placement, cover→login order, light/dark switching, collapse persistence, privacy navigation/active state, 5 responsive widths, no clipping/overflow and no browser errors.
- Existing end-to-end regression check passed for correction, history details, undo, whole-file search and CSV export; table position/size and48px virtual rows remain stable. Inspected desktop light/dark, collapsed, mobile and cover screenshots under Documents/Codex/outputs/dataneat-ui-review/compact-*.

## Automatic cleaning from the manual workspace — 26 October 2026

- Added a visible Automatic cleaning action to the workbook toolbar, reusing the existing survey/missing-label entry handler on the current working copy. It is disabled while cleaning/tool tasks run. No backend changes.
- Frontend production build/TypeScript passed and the frontend was redeployed locally.
- Browser verification passed at1440/1200/1024/390px, light/dark, no page overflow or clipped action. Opening/cancelling the survey preserved data/revision; a real boolean-cleaning run preserved earlier manual duration normalization; undoing that automatic run retained the manual step. Pending missing-label review and its explicit Continue option remained intact. No browser errors.
- Evidence: Documents/Codex/outputs/dataneat-ui-review/manual-to-automatic-review.cjs and manual-to-automatic-*.png.

## Four reviewed cleaning tools — 26 October 2026

- Implemented related-column comparison/arithmetic/conditional-required rules; explicit reviewed recalculation/clearing; persistent exact-cell flags and rename-aware rule references.
- Implemented actual scikit-learn KNN and Iterative numeric imputation with selected helpers, train-only robust scaling, deterministic held-out MAE versus a median baseline, computational limits, prior-estimate exclusion and explicit acknowledgement.
- Implemented bounded multi-column similar-record review, explicit per-conflict field selections, keep-both fingerprints and merge preview identifying the removed original row. Date-format, estimate and accepted-user-value provenance follow selected values through merges and Undo.
- Implemented IQR/MAD outlier checks, grouping, reviewed acceptance/clearing/capping and optional persistent sheet flags. Statistical findings are labelled as review suggestions.
- All four tools share the existing current-copy background jobs, cancellation, owner/revision checks, complete audit, PDF report and replay Undo. Read-only analysis/preview never writes data. Cache schema upgraded to6 without altering stored values/history. Reviewed-tool actions are excluded from transferable recipes. Other four feature proposals were not implemented.
- Production frontend/TypeScript and backend Docker builds passed and both services were redeployed locally. Full current-source backend suite: **517 passed**, two existing deprecation warnings. Focused tests include32 cross-column,38 model,22 matching,3 outlier and11 complete workflow tests.
- Browser QA passed all four tools through actual UI: rule save/flags and arithmetic repair; model analysis/apply/estimate marks; outlier check/save/cap; fuzzy field choices/preview/merge/undo. Verified three viewport widths, light/dark, no horizontal page overflow and no browser errors. Inspected model, matching, dark rules and mobile screenshots.
- Existing browser regression passed correction, History details, Undo, whole-file search, CSV download, stable table position/size, visible Apply, mobile overflow and no sheet animation.
- Evidence: Documents/Codex/outputs/dataneat-ui-review/quality-tools-review.cjs, quality-*.png and review.cjs. Detailed operating limits: docs/reviewed-cleaning-tools.md.
- Later usability ideas (one combined proposed-cleaning review, guided issue flow, fewer initial controls and clearer completion) were discussed only and not added without a further implementation request.

## Six approved usability improvements and Website guide — 26 October 2026

- Implemented all six after explicit approval: combined issue-group plan preview/apply, shared choices across eligible columns, guided type-by-type review, fewer initial cell controls, named reusable browser settings with compatibility checks, and clear completion distinguishing remaining review flags.
- Added explicit multi-column issue replacement scope, restricted to selected flagged cells with identifier guards, complete individual-column audit and replay Undo. No automatic startup preparation or guessed missing/invalid correction was added.
- Added public `/guide`, searchable15-section documentation and sidebar Website guide tab. From an active cleaner it opens separately and preserves the file/revision. Existing theme/collapse preferences remain.
- Production frontend/TypeScript and backend image builds passed; both services redeployed under the existing dataneat Compose project. Final current-source backend suite: **539 passed**, two existing deprecation warnings. New focused coverage:22 tests for suggestions, atomic plans, date provenance, grouped replacements, protection, audit and Undo. Reusable sanitizer and guided queue checks also passed.
- End-to-end browser QA passed on the final deployed build: multi-group preview/apply, settings-change preview invalidation, sanitized save/reuse on another file, guided Fix/Skip/unchanged flags/completion, collapsed advanced controls, one replacement for missing cells in two columns, truthful finish summary,1440/1024/390 widths, light/dark, no page overflow or browser errors.
- Separate guide browser QA passed direct public access,15 sections, KNN/no-results/clear search, anchors and related links, theme/collapse, three widths and new-tab navigation retaining the original upload, revision and values. Inspected final screenshots for legibility.
- Evidence: Documents/Codex/outputs/dataneat-ui-review/simplified-cleaning-review.cjs, simplified-*.png, guide-review.cjs and guide-*.png. Operating contracts: docs/easier-cleaning.md and docs/reviewed-cleaning-tools.md.

## Imputation prerequisite and account files — 28 October 2026

- Production frontend build and TypeScript passed, backend image built, and both services were deployed locally. Health checks returned ok. Full current-source backend suite: **618 passed**, two existing deprecation warnings.
- Imputation now requires the selected column's other live findings to be resolved or explicitly accepted. All estimate methods, manual blank-cell constants, model review/apply, automatic cleaning, plans/recipes and legacy API paths enforce the prerequisite. Existing historical steps remain replayable; new dependent steps protect Undo.
- Real deployed UI checks passed red blocker details, disabled statistical options/KNN/constants, navigation to the offending cell, allowed nonempty correction, and successful marked median after cleanup. Settled desktop/mobile screenshots were visually inspected in both themes: no overflow or footer overlap, no browser errors.
- Account storage tests cover owner isolation, another browser for the same verified account, restart and retention beyond 24 hours, metadata recovery, quotas, stale-job retention choices, and saved-versus-temporary deletion. My files UI checks cover list/search/rename/reopen/delete confirmation and responsive themes, using isolated test-only verified-account responses.
- Created the owner's free Supabase DataNeat organization/project and Google Cloud project DataNeat. After explicit policy and credential-creation approval, created the DataNeat Web OAuth client, saved its secret in Supabase, enabled Google and local authentication, and verified a live Google round trip in the owner's Comet browser. The owner explicitly chose to retain External/Testing until a public site/domain is ready; the allowed test account is the owner's. No fake account or authentication bypass is shipped.
- Real verified-account UI QA passed: synthetic CSV upload, one whitespace correction, Save to my files with no automatic expiry, New spreadsheet preserving the saved record, My files list/quota/revision, rename with original filename retained, and Continue cleaning reopening the corrected copy with its history. Before & after verified the original spaced City value remains preserved. The example Account save test remains on the owner's account. The final frontend build/TypeScript, including the 160-character rename limit and explicit Google-data privacy disclosure, passed and was deployed.
- Saved the owner-requested written credentials in a local private text file with current-user-only permissions. The secret is not included in repository documents or runtime browser code.
- Evidence: Documents/Codex/outputs/dataneat-ui-review/imputation-readiness-review.cjs, imputation-readiness-*.png, account-files-review.cjs, account-files-*.png, google-policy-confirmation.png and account-live-saved-history.png. Provider setup/resume instructions: docs/google-account-setup.md.

## Light dashboard, readability and workbook picker — 2026-10-29

- Full backend suite on the newly built image: **637 passed**, with the two existing deprecation warnings (Starlette/httpx TestClient and openpyxl style-copy test). The new multi-sheet module has **19 passing tests**, covering selected-sheet parsing/export plus read-only inspection, auth/ownership, ZIP/upload/tab limits and invalid/hidden/oversized sheets.
- Production Next.js build, TypeScript and all eight generated routes passed. Manrope is bundled locally with its OFL license; no runtime external font service is required.
- Browser QA used separate loopback-only containers on port 13000, isolated temporary storage and synthetic data. Production Google/Supabase authentication was not disabled or bypassed. Real account configuration remained enabled on port 3000.
- Confirmed no data metrics before upload; four-stage card navigation; off-white light canvas and dark sidebar; body 17px; retained 48px virtual rows; theme switching and no horizontal page overflow at 1440/1000/390px. Visually inspected desktop light/dark upload, actual-data Explore preview, correction popup and mobile sheet screenshots.
- Real XLSX UI flow: no analysis before explicit sheet selection; leading-zero IDs and formula text retained; only selected columns loaded; dirty-sheet switching prompts before replacement; Keep cleaning retains corrections; Leave anyway opens the chosen other sheet; restored files explain the original-workbook requirement.
- Additional fixture confirmed empty first and header-only tabs disabled, valid hidden tab labeled/selectable, cancellation leaves the workspace unchanged, and selection resets when reopening the picker. Cover, login, guide, privacy and files layouts passed desktop/mobile overflow checks.
- Evidence: `Documents/Codex/outputs/dataneat-ui-review/light-dashboard-workbook-review.cjs`, `dashboard-review-results.json`, `workbook-edge-typography-review.cjs`, `dashboard-*.png`, `workbook-picker-*.png`, `font-*.png`, `multi-sheet-navigation-check.xlsx` and `workbook-picker-edge-cases.xlsx`.
- Temporary friend-sharing instructions were prepared in `docs/temporary-friend-sharing.md`. No tunnel/public deployment was started and no provider access lists were changed.
- Final production smoke on port 3000 passed cover → login, enabled Google button, 17px body text and rejection of unauthenticated workbook inspection (401), with no browser errors. Test-only containers/network were removed; the two normal DataNeat containers remain running.

## Sidebar Logout and synthetic test workbook — 2026-10-29

- Removed the top account/email bar. Logout now lives at the bottom of the signed-in sidebar, including collapsed and mobile layouts. My files navigation remains available. Admin Usage overview remains an admin-only sidebar action and opens in a native dialog.
- Frontend production build and TypeScript passed. Browser checks with isolated test-only auth responses passed both themes at 1440/1024/390px, no account email bar, sidebar placement, collapsed icons, no page overflow, preserved admin report access/Close, server and Supabase logout, workspace/account cache removal, and return to Google login. No browser errors. Real owner credentials/session were not used or signed out. Evidence: `Documents/Codex/outputs/dataneat-ui-review/sidebar-logout-review.cjs` and `sidebar-logout-*.png`.
- Created `Documents/Codex/outputs/01a136e4-87a0-7480-af1f-19dacaf13404/DataNeat-Multi-Sheet-Test.xlsx`: five data tabs with 512 invented records plus a 23-row Guide. Artifact Tool authored/recalculated/inspected/rendered every tab. Read-only saved-file checks confirmed intentional dirty labels, true blanks, leading-zero text IDs, typed values where intended, and no executable formulas.
- Added worksheet bounds metadata omitted by the spreadsheet exporter using ZIP/XML metadata repair, without changing authored cell data/styles. The actual DataNeat inspector accepts all six tabs, leaves selection null, and the parser reads each expected row count. This workbook was not uploaded to the owner's account.

## Explore metric layout and section spacing — 2026-10-29

- Moved the four real metrics into uniform cards under the full-width preview. Responsive container queries select 4/2/1 columns; labels and values never wrap. Kept 25px numeric text and added 32px before the cleaning-method heading.
- Production frontend build/TypeScript passed and the local frontend was recreated. Layout QA used an isolated browser fixture with the actual deployed CSS and font assets, without accessing the owner's data or changing authentication. All 28 combinations passed across seven widths (320,390,650,768,900,1024,1440), both themes, the reported 568,000 example and maximum 20,000,000 stress values: single-line text, no clipped digits/page overflow, uniform card dimensions and the full 32px gap. Desktop dark and mobile light screenshots were visually inspected.
- Evidence: `Documents/Codex/outputs/dataneat-ui-review/metrics-layout-review.cjs` and `metrics-spacing-*.png`. Only presentation CSS changed; backend tests were not rerun for this layout adjustment.

## October 30, 2026 — column types and XLSX presentation

- Full backend suite: 678 passed. Final focused suite: 45 passed (column-type choices, original colors, saved formula results); existing Starlette test-client deprecation warning remains.
- Type tests cover overriding misleading Phone/Email/Salary headings, all 18 explicit choices, numeric-imputation eligibility, value/leading-zero preservation, Auto, undo, rename and coordinate axes/pairs.
- Original-fill tests cover opt-in behavior without data/revision/history mutation, RGB/indexed/theme fills, selected sheet, renamed/paged columns, duplicate-row survivor alignment and unsupported CSV.
- Formula tests cover cached result types, absent-cache rejection, selected-sheet isolation, literal equals-prefixed strings, exports and preservation of originals.
- Production frontend build and TypeScript passed. Browser QA: outputs/dataneat-ui-review/column-presentation-review.cjs and column-presentation-results.json under Documents/Codex. Real synthetic 80-row workbook on separate localhost:13000 containers; original-color toggle, cached numeric formula results, column settings saves, scrolling, 48px row geometry, dark/light/mobile. No browser page errors.
- Existing owner authentication and persisted files were not used or changed for testing.

## November 23, 2026 — capacity raise, read-only review links, optional assistant

- Benchmarked upload → workflow initialization on this machine with a 10-column synthetic file: 1k rows 1.1s upload / 1.4s init; 5k 5.3s / 7.2s; 10k 9.6s / 13.7s; 25k 27.3s / 36.6s, peak process RSS 143 MB. The public caps were set from that curve.
- Public beta caps raised from 2 MiB / 10,000 rows / 50 columns to 5 MiB / 15,000 rows / 75 columns, with a 250,000-cell analysis budget, a 300 MB snapshot budget, 200 stored records and 30 saved files / 40 MiB per account.
- Added read-only, revocable, expiring review links (`/share?t=...`, public `GET /api/share/{token}` and its PDF route). Tokens are HMAC-signed with a per-file share epoch; editing, the original upload and the owner's workspace remain inaccessible.
- Added the optional bring-your-own-key assistant (`POST /api/assist`): fixed provider presets, consent required, key never stored or echoed, suggestion-only application through the existing rules decision. `AI_ASSIST_ENABLED=false` disables it.
- Backend full suite: 711 passed. Two pre-existing failures were corrected: a platform-specific CSV newline assertion and a literal schema-version assertion (now compared with `ANALYSIS_SCHEMA_VERSION`).
- Frontend TypeScript and production build passed; static export passed and includes `share.html` (66 files, 1.8 MB).
- Deployed the verified backend files and static export to `https://arsany.pythonanywhere.com/` after backing up the replaced backend files. Live checks: `/api/health` reports the new caps; `/`, `/login`, `/guide`, `/privacy`, `/workspace` and `/share` return 200; `/api/share/invalid` returns the new 404 message; all 19 referenced `_next` assets return 200; `/api/auth/config` still reports authentication enabled.
- Not verified live: authenticated share creation and an assistant call, because both need the owner's sign-in. PythonAnywhere free accounts must whitelist the provider hosts before the assistant can reach them.
- Not done: the cross-process job/lock refactor for multi-worker hosting (deliberately deferred with the host migration).

## November 23, 2026 — manual-first cleaning entry

- Explore no longer offers cleaning methods. It shows one "Start with a manual review" card with "Open the spreadsheet". The "Review suggested fixes" entry was removed from Explore, the workbook toolbar, and the guided-walkthrough completion.
- Guided cleaning and Automatic cleaning are available in the workbook toolbar (and the Tools drawer survey) immediately when the sheet opens; no prior change is required. An intermediate gated build (buttons after the first recorded change) was removed the same day at the owner's request.
- Updated the website guide's quick start, faster-cleaning, and automatic-cleaning sections to match. Saved choices still opens its existing modal; its internal Suggested-fixes tab is the source for building reusable choices and was left intact.
- Static export rebuilt (66 files) and deployed to PythonAnywhere. Verified: the deployed workspace's 19 referenced JS chunks all return 200, none contain the removed "Review suggested fixes" label, and no stale gating copy remains.
- Real-browser check against the same build with headless Chromium: upload → Explore shows no cleaning-method buttons; opening the sheet shows Guided and Automatic immediately; the quick-review label is absent. Screenshots `ui-explore.png` and `ui-sheet.png` are in the session workspace.
- TypeScript, production build, and static export passed. No backend behavior changed.

## November 23, 2026 — automatic-cleaning survey restyle

- Numbered the survey questions (1–6, including the duplicate-rows question) with round green badges; question labels use the product green while the selected answer inside each select keeps the normal text color. Question spacing increased from 18px to 30px (24px on narrow screens).
- Presentation-only: `frontend/app/auto-cleaning-survey.css` is imported last in the layout. Question order, choices, column exceptions, saved choices and cleaning behavior are unchanged.
- Verified in headless Chromium: six numbered questions, 30px spacing, and distinct question/answer colors in light and dark. Screenshots `ui-automatic-light.png` and `ui-automatic-dark.png`.
- Static export rebuilt (66 files) and deployed. Live: the workspace CSS bundle returns 200 and contains the new survey rules; `/workspace` and `/guide` return 200.
- TypeScript, production build and export passed.

## November 23, 2026 — date interpretation resolves ambiguous values

- Choosing Day first or Month first now rewrites ambiguous dates in the chosen output format in both automatic and manual cleaning. For example, day-first with YYYY-MM-DD turns 05/10/2025 into 2025-10-05 and 01/02/2024 into 2024-02-01.
- Automatic cleaning applies the date question to columns the user explicitly declared as Date or Date and time, not only auto-detected date columns.
- Manual cleaning offers explicit quick corrections "Resolve ambiguous dates as day first" and "Resolve ambiguous dates as month first", alongside the existing interpretation control, and states when ambiguous values are being preserved.
- The automatic survey example now picks an ambiguous sample and shows the resolved result instead of an unambiguous one.
- Tests: seven new cases (automatic day-first/month-first resolution, preserve, unambiguous-only, manual day-first, manual preserve, declared-date column). Full backend suite: 721 passed. TypeScript and production/static build passed.
- Browser check: automatic run rewrote the ambiguous dates in the sheet; the manual correction offered and applied the day-first resolution. Screenshots `ui-dates-example.png`, `ui-dates-manual.png`.
- Deployed the backend file (remote hash verified equal) and static export to PythonAnywhere. Live: workspace/guide/privacy return 200 and the deployed chunks contain the new resolution labels.
- Unchanged principle: ambiguous dates are never guessed. They are resolved only when the user chooses a pattern; "Keep ambiguous dates" still preserves them.

## November 23, 2026 — missing-value findings visible and navigable

- Column headers counted missing-value flags while cell rendering, the issue drawer and the issue navigation hid them. A column could therefore show "2 issues" yet report "No issues detected in this column."
- N/A, null, "-" and similar labels are now rendered as flagged cells, listed in the issue drawer and in the column navigation, and open the Convert labels to empty / Keep as text decision in the cell panel.
- Genuine empty cells stay visually unmarked in the sheet to avoid clutter; they are listed in the navigation and issue drawer and route to the Imputation phase, where they are completed.
- Detection, counts, corrections, audit and undo are unchanged; this is a presentation/routing fix.
- Browser check: three missing-label cells rendered; the Salary navigation shows the missing-value guidance instead of "No issues detected"; First issue + Fix this issue opens the marker decision panel; an empty-cell column navigates to Imputation.
- TypeScript, production build and static export passed. Deployed; the live chunks contain the new guidance text.

## November 24, 2026 — percentage scale foundation (Phase A) and type cleanup

- Bare numbers in a percentage column (for example 0.96) are now flagged with a `percentage_scale` review issue until the column declares whether they mean percentage points (0.96 = 0.96%) or ratios (0.96 = 96%). The flag appears in the header count, issue drawer, navigation, Insights and cell panel; the cell panel opens Column settings.
- Column settings gains a "Bare numbers without %" control for percentage columns, including auto-detected ones. The choice is stored in the existing `percentage_scale` column rule, so it is recorded, undoable and travels with rename, recipes and saved files. Declaring it does not rewrite cells.
- Gates: mean/median requires a declared scale for bare percentage values (ratio scales ×100, points stay); imputation readiness blocks on the new issue; column-rule bounds require the scale; cross-column arithmetic rejects bare percentage columns until normalized; automatic cleaning skips undeclared percentage columns with a reason.
- Analysis schema advances to 10 so existing files refresh findings without changing data, history or revision.
- Removed the redundant "Salary / numeric amount" type from the picker, column rules and AI suggestions. Existing `salary` rules remain accepted by the backend for compatibility and display as Number; no saved data is rewritten.
- Tests: `test_percentage_scale.py` (7 cases) plus updated percentage-imputation tests; full backend suite **729 passed**. TypeScript and production/static build passed.
- Headless browser: Rate column with 0.96/0.84/0.60 shows 3 flags → panel explains both meanings → Column settings → Ratio → Save → 0 flags; the type picker no longer offers Salary. Screenshot `ui-percentage-scale.png`.
- Deployed the nine changed backend files (backed up first) and the static export; live workspace chunks contain the new scale UI and no Salary option.

## November 24, 2026 — full premium design system

- Replaced the application's visual layer with `frontend/app/premium-theme.css` (imported last): dark-first tokens (`#0B0F19` base, `#1F2937` panels, `#10B981` mint accent), Inter typography, restyled sidebar with a 3px active indicator, global form controls, secondary/primary buttons, cards, modals, issue pills and the spreadsheet skin.
- Self-hosted Inter Variable was added with its OFL license; there is no runtime font request. Monospace fallbacks are used for data where applicable.
- Dark mode is the default for new visitors; existing saved theme preferences are respected and light mode was restyled to the same system. The sidebar stays dark in both themes.
- Restyled cover, login, upload/Explore, spreadsheet, automatic-cleaning modal, column settings, My files, guide, privacy and shared-review surfaces. The sheet keeps exact 48px rows and all virtualization behavior; correction panels are clamped away from the sidebar on desktop.
- No workflow, API, audit, export or storage behavior changed.
- Production build, static export and TypeScript passed. Headless Chromium reviewed every major screen in dark and light plus a 390px mobile viewport with no page errors. The deployed site returns 200, applies the dark default, serves the local Inter font, and computes mint primary buttons with dark text.
- Live deployment of the static export verified; screenshots captured for cover, login, upload, Explore, sheet, automatic cleaning, settings, files, guide, privacy, light and mobile.

## November 24, 2026 — upload 504 and multipart fixes

- Root cause of “Server returned an invalid response” on upload: the host proxy returns HTML 504 at 60 seconds. The access log showed `POST /api/files/upload 504 response-time=60.039`; profiling on the host takes 15s at 50k cells, 49s at 150k and >60s at 240k, so parsing + profiling + snapshot save exceeded the ceiling.
- Uploads above 40,000 cells now return immediately and complete profiling/planning in a background task; the UI polls `GET /api/files/{id}/analysis` and shows “Preparing your data summary…”. Small files remain synchronous. Pending uploads restore correctly after reload.
- Starlette's 1 MiB multipart part limit was raised to the configured upload budget, fixing 1–5 MiB uploads that previously returned HTTP 400.
- Upload errors now report the HTTP status instead of a generic invalid-response message; unexpected API exceptions return JSON.
- Added tests for pending-then-ready analysis, queued polling and >1 MiB multipart uploads. Full suite: **732 passed**. Local browser: 240k-cell upload completed async in ~35s with no errors; 40-row file opened in ~0.3s. Host background-task execution verified live; backend and static export deployed (200 responses).

## November 24, 2026 — issue-specific corrections and upload speed

- Cell correction menus now derive from the cell’s actual issue kinds and the column’s detected type. Phone issues show only “Standardize phone format” and manual correction; currency, URL, boolean, whitespace and email cases were verified, with email/type-mismatch offering only manual correction. The quick-correction selector and suggested correction use the same mapping.
- Hosted uploads now always return before profiling. The upload path writes only the local temporary snapshot; the background analysis performs the cloud commit. Remote snapshot latency was previously included in every upload (measured ~8.8s per upload in the access log).
- Polling is adaptive: 500ms for the first 8 seconds, then 1.5s, so small files open noticeably sooner without flooding the host.
- Measured before: upload response 8.8s, analysis reported ready after ~65s for a large file. After: local upload + analysis for a small file completes in <1s; upload response no longer waits for analysis or the remote snapshot. Full backend suite re-run after the storage change: **732 passed**.
- Excel add-in proposal written in `docs/excel-addin-plan.md` (not implemented).

## November 24, 2026 — Excel add-in Tier L preview

- Added `excel-addin/`: local HTTPS companion, Office.js task pane, validated sideload manifest, certificate/setup scripts, bundled Inter font and README. Backend adds read-only `POST /api/addin/analyze` returning column summaries and compact per-cell issue markers.
- Real Excel 365 desktop test: task pane loaded from `https://localhost:9443`, analyzed a test sheet and returned 17 flagged cells across 6 columns; manifest validated with Microsoft's validator.
- The test machine's Excel is unlicensed, so Office.js formatting returned AccessDenied (“You cannot perform the requested operation”). Analysis works; highlighting requires a licensed/signed-in Excel and an editable workbook (Enable Editing). The task pane now explains this instead of failing silently.
- Added tests for the add-in analysis endpoint and cap/truncation. Full backend suite: **735 passed**. Add-in code committed and pushed to GitHub.

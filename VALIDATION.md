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

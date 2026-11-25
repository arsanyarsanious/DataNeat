# DataNeat Security Review

**Date:** 2026-11-25
**Scope:** current repository `main` (around `b7b1510`), backend API, frontend auth/share flow, storage, AI assist, Excel add-in companion and deployment notes.
**Method:** source review, route/auth mapping, live endpoint probes (no credentials used), cross-session authorization tests, secret-pattern scans of tracked files, and dependency review. No destructive tests and no real user data were used.
**Secrets:** no secret values are included in this report.

## Executive summary

The main web application has a sound authorization model: all file/job/workflow reads are scoped through a server-side session or account owner, share tokens are HMAC-signed and read-only, uploads are not treated as pickles, and requests without a valid session were rejected in the tested production configuration.

The highest-risk issue is not in the hosted web app: **the Excel-on-the-web test path initially exposed an unauthenticated local companion through a public Cloudflare quick tunnel, with a broad `*.trycloudflare.com` CORS allow-list.** The companion now requires a persistent per-installation add-in token on `/api/addin/*`, the broad CORS regex was replaced by a same-origin check, and the tokenized tunnel path was verified end-to-end. The tunnel remains a temporary testing channel and must be stopped when not in use.

The second issue was **temporary diagnostics in production**. They have now been removed from the repository and the live configuration, and `/api/health` no longer exposes disk capacity. The fail-closed `REQUIRE_AUTH` guard is implemented and enabled live; see the P0 verification section.

No real server-side API keys were found in tracked files or the current worktree. One test contains a deliberately fake `sb_secret_…` string. `.env` is untracked and contains only the Supabase URL and publishable key; the service-role key is not in it. Local packaging risk remains because the untracked `.env` and the add-in certificate private key exist in the working folder.

## Findings

| ID | Severity | Area | Finding |
|---|---|---|---|
| SEC-1 | **High** — mitigated 2026-11-25 | Excel companion | Public quick tunnel exposed an unauthenticated local API; broad CORS regex |
| SEC-2 | **High** — fixed 2026-11-25 | Diagnostics | Temporary diagnostics, log tail, CPU benchmark and disk fields were still in production code/config |
| SEC-3 | **Medium** — mitigated 2026-11-25 | Authentication | Authentication fails open when Supabase env is absent; public deployments can silently become anonymous |
| SEC-4 | **Medium** | Availability | Per-IP in-memory rate limiting, unbounded rate map, single worker, CPU/zip-expansion DoS |
| SEC-5 | **Medium** | Share links | Bearer token in URL query; visible in browser history, access logs and Referrer |
| SEC-6 | **Medium** | Browser hardening | No CSP, HSTS, Referrer-Policy, X-Frame-Options/frame-ancestors |
| SEC-7 | **Low/Medium** | AI assist | User provider key persisted in localStorage/sessionStorage in plaintext, with no CSP layer |
| SEC-8 | **Medium (local)** | Companion TLS | Self-signed CA certificate and unencrypted private key trusted in CurrentUser Root |
| SEC-9 | **Low** | Session lifecycle | Logout does not revoke the Supabase token server-side; logout is CSRF-able |
| SEC-10 | **Low** | Information exposure | Public `/docs`, `/openapi.json`, `/api/health` disk details; no secrets but useful reconnaissance |
| SEC-11 | **Info** | Dependencies | No automated CVE audit was completed; versions are pinned but not verified against an advisory database |

### SEC-1 — Public Excel companion (High)

**Status:** Mitigated 2026-11-25. `run.ps1` now generates/persists a 32-byte
add-in token and writes a tokenized local manifest. `web-tunnel.ps1` embeds the
token in the generated web manifest; the task pane sends it as `X-Addin-Token`.
The API rejects missing/wrong tokens with 401, and the broad trycloudflare CORS
regex was removed in favor of a same-origin Host/Origin check. The tokenized
tunnel path and browser Analyze flow were verified. The tunnel is still
temporary; stop it when done and do not share generated manifests.

Historical description follows.

**Affected files**

- `excel-addin/companion/run.ps1`
- `excel-addin/companion/web-tunnel.ps1`
- `backend/app/main.py` (optional `ADDIN_TOKEN` enforcement; same-origin Host/Origin check; historical broad CORS regex)

**What happens**

`run.ps1` clears the Supabase variables and runs the existing FastAPI app with authentication disabled. `web-tunnel.ps1` creates a public `https://*.trycloudflare.com` tunnel to that local server and generates a manifest pointing at it. The companion also accepts requests whose Origin matches `https://([a-z0-9-]+\.)?trycloudflare\.com` via `CORS_ORIGIN_REGEX`.

**Impact**

- Anyone who obtains the tunnel URL can use the local engine: upload/analyze files, consume CPU and storage, and reach public/debug paths.
- A page hosted on any `*.trycloudflare.com` origin can make browser requests to the local companion under the broad CORS rule. With no add-in token, the request does not need a victim session.
- The task pane and its API traffic traverse Cloudflare. Sheet contents are sent from the browser through the tunnel to the local engine; this expands the privacy boundary beyond “processed locally”.
- The tunnel URL was shared during testing and may exist in chat/terminal logs/history; it should be treated as compromised.

It is *not* a direct cross-user account breach: file records are still session-scoped, and the companion has no account data. The practical risk is unauthorized compute/storage use, denial of service, local-engine abuse and data-path exposure.

**Mitigation**

- The tunnel/companion can be started only with the tokenized manifests now; no-token Analyze returns 401.
- The tokenized tunnel and same-origin browser Analyze were verified 2026-11-25.
- Prefer Cloudflare Access (or a private tunnel) for any remote Excel-web testing.
- Do not leave the tunnel running unattended; rotate the URL and verify it is closed afterward.
- For packaged distribution, do not expose the local server at all.

### SEC-2 — Production diagnostics and disk details (High cleanup)

**Status:** Fixed 2026-11-25. The diagnostics endpoints and disk fields were
removed from `backend/app/main.py`, `public_paths` was reduced, `DIAG_TOKEN` and
`ERROR_LOG` were removed from the live config, and the live host was reloaded.
Live `/api/health` now returns only:

```json
{"status":"ok","max_upload_mb":5,"max_rows":15000,"max_columns":75}
```

`/openapi.json` no longer lists any diagnostics paths; unauthenticated requests
to those old paths return 401 from the auth guard, not route data. The token was
removed (equivalent to rotation, since the capability no longer exists).

**Affected code (historical)

- `backend/app/main.py`: `/api/diagnostics/tail`, `/api/diagnostics/benchmark`, `/api/diagnostics/background`, `/api/diagnostics/background-status`; `DIAG_TOKEN` checks; `/api/health` disk fields.
- Pre-fix live configuration contained a diagnostics token (`DIAG_TOKEN`) and an error-log path; both were removed 2026-11-25.

**Evidence**

- `/api/health` on the live host returned `disk_total_mb`, `disk_free_mb` and `storage_mb`.
- Diagnostics routes returned 404 without the token, confirming they are present but token-gated.
- The token is compared with normal string comparison and is stored in private host configuration.

**Impact**

If the token leaks (logs, shell history, screenshots, support access), an attacker can read the error log tail, which can include IP addresses, stack traces, request paths and possibly share URLs/tokens, and can run the CPU benchmark repeatedly. Disk information also helps target capacity/DoS. These endpoints have no product purpose in production.

**Mitigation**

1. Delete the diagnostics endpoints, disk fields from `/api/health`, and `DIAG_TOKEN` configuration.
2. Rotate the token before deletion (treat it as exposed).
3. Remove the diagnostics paths from `public_paths`; reduce public routes to health/auth/share needs.
4. Deploy the cleanup; repository cleanup alone does not remove the live endpoints.
5. Make `health` return only `{status, limits}` needed by monitoring.

### SEC-3 — Authentication fails open (Medium)

**Status:** Mitigated 2026-11-25. Added a `REQUIRE_AUTH` guard: when set to
`true`, any non-public API request returns 503 if Supabase URL/key are absent or
invalid. The guard preserves `/api/health`, `/api/auth/config` and read-only
`/api/share/*` links. Live config now has `REQUIRE_AUTH=true` (stored as a
string because PythonAnywhere copies config values into `os.environ`). The guard
is covered by tests; hosted behavior with a valid config remains 401 for
anonymous protected requests.

`backend/app/main.py` enables authentication only when `identity.configuration()["enabled"]` is true. `identity.configuration()` returns enabled when either `SUPABASE_URL` or the publishable key is non-empty. If both are absent — a missing env file, a bad deploy, or a fresh host — all non-public APIs are served without authentication.

Files remain session-scoped, so an attacker cannot automatically read another user's file. The exposure is anonymous service use: uploads, analysis, cleaning jobs, temporary storage and CPU. The sign-in UI also silently becomes “local workspace” mode.

**Mitigation**

- Use `REQUIRE_AUTH=true` on public deployments (implemented and enabled live); keep the current anonymous mode only for localhost/desktop companion builds.
- Validate configuration at startup rather than first request.
- Keep the current anonymous mode only for localhost/desktop companion builds.
- Document the required production env as a deployment precondition.

### SEC-4 — Resource exhaustion and rate limiting (Medium)

**Affected code**

- `main.py` in-memory `rate` dictionary and 120 requests/minute per `request.client.host`.
- `MAX_UPLOAD` / parser expanded-size limit (100 MB) and single-worker deployment.
- ThreadPool job queue and CPU-bound pandas/scikit-learn work.

**Impact**

- The rate map is never pruned for inactive IPs, so a high-cardinality client set can grow memory.
- Rate limiting is per process and per IP, not per account; behind a proxy, IP handling must be correct.
- An authenticated or public client can repeatedly send a small compressed XLSX that expands substantially, or expensive cleaning jobs, and monopolize the single worker.
- The tunnel path (SEC-1) amplifies this because no authentication is required.

**Mitigation**

- Bound/prune the rate map (LRU or periodic sweep).
- Add per-account quotas and concurrency limits for uploads, analyses and jobs.
- Enforce decompressed-size and time budgets in the parser/profiler.
- Put the public host behind a WAF/proxy with request timeouts; keep CPU work off the request path.
- Add an alert for sustained 429/413/5xx rates and worker saturation.

### SEC-5 — Share tokens in URLs and logs (Medium)

`frontend/app/share/page.tsx` reads the token from `?t=...` and calls `/api/share/{token}`. The token is a bearer secret with a default 7-day and maximum 30-day lifetime.

**Impact**

The token can appear in browser history, screenshots, chat, server access logs and any Referer sent to another origin. The diagnostics log tail (SEC-2) increases the chance of log exposure. Possession grants read-only access to the 25-row preview, file name, cleaning summary and PDF.

**Mitigation**

- Add `Referrer-Policy: no-referrer` to the share page and API responses.
- Redact/query-strip share paths from access logs.
- Keep the 7-day default and encourage revocation after review; consider shorter maximum TTL.
- Optionally exchange the URL token for a short-lived httpOnly session cookie and remove it from the URL.

### SEC-6 — Missing browser security headers (Medium)

Live root response included only `x-content-type-options: nosniff`; no CSP, HSTS, Referrer-Policy or frame-ancestors/X-Frame-Options. API responses add `Cache-Control: no-store` and `nosniff`, but static pages have no CSP.

**Impact**

- No defense-in-depth against XSS; any future injection can read Supabase tokens or the AI key from browser storage.
- Share tokens can leak through Referer without a restrictive policy.
- Pages can be framed for clickjacking (the Office task pane is a separate origin and should not inherit a blanket `DENY`).

**Mitigation**

- Add HSTS at the proxy/host.
- Add `Referrer-Policy: no-referrer` (especially `/share`), `X-Content-Type-Options`, and a CSP compatible with the static Next build and Office.js.
- Add `frame-ancestors` for web pages; keep the task pane’s framing requirements separate.
- Test the CSP against Next’s inline runtime before enforcing.

### SEC-7 — AI provider key stored in browser storage (Low/Medium)

`frontend/components/ai-assist-panel.tsx` stores the user’s provider key in `localStorage` when “Remember this key on this device” is checked, otherwise in `sessionStorage`, in plaintext. The server does not store or log the key, which matches the privacy page, but the browser storage is readable by any script on the origin, browser extensions and anyone with the device profile.

Because the app has no CSP (SEC-6), a future XSS or compromised dependency would expose the key along with the Supabase session. The same risk applies to Supabase’s persisted session token.

**Mitigation**

- Keep the key session-only by default and add an explicit warning for “remember” mode.
- Provide a “Forget key” action that clears both storages.
- Add a CSP and avoid third-party scripts on the workspace origin.
- Consider a server-side encrypted secret store or provider OAuth instead of browser persistence.

### SEC-8 — Companion certificate design (Medium, local)

`excel-addin/companion/certs.py` creates a self-signed localhost certificate trusted in the current user’s Root store. The generated certificate has CA basic constraints and the private key is an unencrypted file under the gitignored `companion/certs` folder.

**Impact**

A local process or user with access to that key can impersonate the localhost service or intercept local traffic. Trusting a CA in the user Root store is broader than trusting one leaf certificate for `localhost`. The private key is also present in the portable project folder, so zipping the folder for testers could expose it.

**Mitigation**

- Generate a leaf certificate (`CA:false`, `serverAuth`, SAN `localhost`/`127.0.0.1`) and trust only that leaf.
- Restrict key file ACLs to the current user; consider DPAPI/encrypted storage.
- Document certificate removal.
- Exclude `certs/`, `.env`, tunnel logs and generated manifests from any distribution package.

### SEC-9 — Session/logout lifecycle (Low)

Logout deletes the auth cookie and clears the in-process verification cache, but does not revoke the Supabase access token; a stolen token remains valid until Supabase expiry (cookie `max_age=3600`). `/api/auth/logout` is public and can be triggered cross-site (logout CSRF). The auth cookie uses `HttpOnly`, `SameSite=Lax`, and `Secure` on the live host; the origin check blocks disallowed POST/DELETE origins.

**Mitigation**

- Accept the short token lifetime, or call Supabase sign-out/revocation on logout.
- Consider requiring an authenticated POST for local logout or include a CSRF token.
- Keep `Secure` and `SameSite` enforced in hosted configuration; validate at startup.

### SEC-10 — Reconnaissance surface (Low)

**Status:** Health disk fields and diagnostics docs were removed in the P0
cleanup. `/openapi.json`, `/docs`, `/redoc`, `/api/health` and
`/api/auth/config` remain public. The auth config deliberately exposes the
Supabase URL and publishable key (public by design); health now returns only
status/limits. OpenAPI reveals the full API surface.

**Mitigation**

- Disable docs/OpenAPI in production unless needed.
- Keep publishable Supabase details public; never expose the service-role key.

### SEC-11 — Dependency review not completed (Info)

`pip-audit` was not available in the backend environment and could not be installed there (no `pip` module in the harness venv), and no package-registry audit was run. Backend and frontend versions are pinned, but this review did not verify them against current CVE advisories. Re-run an audit in the deployment environment:

```bash
pip-audit -r backend/requirements.txt
pnpm audit --prod
```

## Authorization review

### Confirmed controls

- Authentication is server-side: the cookie token is verified against Supabase `/auth/v1/user`; local JWT payload parsing is used only for cache TTL, not as the authorization source.
- File, editor, workflow and job routes resolve records through `request.state.session`; cross-session access returned 404 in testing.
- Account-file routes require a verified user and stable account session, and check `account_owner`.
- Admin usage requires an administrator email.
- Share routes are read-only; creation/revocation require the owner session.
- Share token signature uses HMAC-SHA256 with constant-time comparison and epoch/expiry checks.
- AI assist requires consent, a supported provider allow-list, and a session-owned file; the provider base URL is fixed.
- Uploaded bytes are never unpickled. Cloud snapshots are HMAC-verified before `pickle.loads`; local snapshots are server-created files with 0600 permissions.
- Formula-injection escaping is applied to CSV/XLSX exports; PDF text is HTML-escaped.
- XLSX parsing checks total decompressed size (100 MB), and row/column limits are enforced.
- CORS rejects disallowed POST origins and does not reflect arbitrary origins in hosted mode.
- The static site blocks `/api` fallbacks and uses `nosniff`; API responses are `no-store`.

### Tested boundary evidence

Using a fake Supabase configuration to enable auth (no valid token):

| Request | Result |
|---|---|
| `GET /api/health` | 200 (public) |
| `GET /api/auth/config` | 200 (publishable config only) |
| `GET /api/files/{id}/workspace` | 401 |
| `GET /api/account/files` | 401 |
| `GET /api/admin/usage` | 401 |
| `POST /api/addin/analyze-json` | 401 |
| `GET /api/share/not-a-token` | 404 (signed-token route only) |
| `GET /api/diagnostics/tail` | route removed; old path now auth-wrapped 401 (was 404 with no token) |
| `POST /api/files/upload` | 401 |
| `GET /api/unknown` | 401 (auth wraps `/api`) |

Cross-session test with two browser sessions: owner `GET workspace` → 200; second session → 404 for workspace and editor. A share token allowed public read but did not provide an edit path. An `Origin: https://evil.example` upload was rejected 403 on live; a request with no Origin reached auth and returned 401.

### Authorization exceptions

- **Excel companion:** no Supabase user auth, but `/api/addin/*` requires the persistent add-in token; same-origin CORS. See SEC-1.
- **Diagnostics:** removed; no token endpoint remains.
- **Auth-disabled deployments:** see SEC-3.
- **Share links:** intentionally public to anyone with the token; see SEC-5.

No IDOR or missing owner check was found on the main web API routes reviewed.

## Secrets review

- No real server-side keys were found in tracked files.
- A tracked test uses a deliberately fake `sb_secret_should_never_be_public`; it is not a credential. The test asserts that a service-role-like key is never returned by `/api/auth/config`.
- `.env` is untracked/ignored and contains only `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `GOOGLE_SIGN_IN_ENABLED`. The service-role key is not present. The publishable key is public by design.
- `.env.example`, `deploy/RENDER.md`, `render.yaml` and `deploy/supabase-storage.sql` reference secret *names* and placeholders, not values. RLS revokes table/function access from `anon`/`authenticated` and grants only `service_role`.
- No tracked `.pem`, `.key`, certificate, `.env` or generated tunnel manifest exists.
- Untracked local artifacts remain sensitive: `.env` and `excel-addin/companion/certs/` private key. Exclude them from any package or support upload.
- The Cloudflare quick-tunnel URL is a bearer capability; the current temporary test tunnel is token-protected but should still be treated as sensitive and stopped when finished.

## Remediation order

### Now / P0

1. **Done:** companion token auth and same-origin CORS implemented; tokenized tunnel/browser flow verified. Keep the tunnel temporary and stop it when not testing.
2. **Done:** Removed diagnostics endpoints, disk fields, `DIAG_TOKEN` and related `public_paths`; removed the token/log-path config; redeployed the live host and verified minimal health/OpenAPI.
3. **Done:** Added a production `REQUIRE_AUTH` guard so missing Supabase configuration fails closed; live config enables it.

### Next / P1

4. Add per-account quotas and bounded rate limiting.
5. Add share `Referrer-Policy`, log redaction and CSP/HSTS headers.
6. Replace the companion CA certificate with a leaf cert and restrict the private key.
7. Warn about/clear browser-stored AI keys; default to session-only.
8. Add server-side logout/revocation (or document the token lifetime).

### Later / P2

9. Disable public API docs in production.
10. Run dependency CVE audits and add them to CI.
11. Add security regression tests for auth boundaries, CORS, share revocation and companion token auth.

## P0 verification (2026-11-25)

- Local suite: **741 passed**, including tests for fail-closed auth,
  configured-auth rejection, diagnostics removal, add-in token enforcement and
  same-origin tunnel CORS.
- Live `/api/health`:
  `{"status":"ok","max_upload_mb":5,"max_rows":15000,"max_columns":75}`.
- Live `/openapi.json` contains no diagnostics paths.
- Live unauthenticated protected requests return 401; invalid share tokens
  return 404.
- Tokenized add-in tunnel: task pane tokenized, no-token Analyze 401, token
  Analyze 200, Chromium Analyze passed, and both generated manifests validate.
  The current tunnel is temporary and should be stopped after testing.
- Live config: `REQUIRE_AUTH` is the string `"true"` (a JSON boolean would crash
  the PythonAnywhere launcher, which copies config values into `os.environ`);
  `DIAG_TOKEN` and `ERROR_LOG` are absent.
- Deployment note: the P0 patch was applied to the live `main.py` as a minimal
  change, not as a full deploy of the current repo backend.

## Residual risks

- The live deployment is behind the repository; the P0 cleanup was deployed as a
  minimal patch of the live `main.py`, not the full current repo backend. A full
  deployment still needs the normal test/browser/rollback process.
- Single-worker architecture means any CPU/memory DoS affects all users until migration to the documented multi-worker design.
- The Excel add-in is a local preview with a manually trusted certificate, not a packaged/signed product; its threat model changes once distributed to other users.
- Full git-history secret scanning was not completed in this pass; only the current tracked tree/worktree was scanned.
- Dependency advisories were not checked (SEC-11).

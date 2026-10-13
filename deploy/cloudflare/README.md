# Cloudflare frontend deployment

This configuration publishes DataNeat's static Next.js frontend and a same-origin API gateway to Cloudflare Workers. It does not publish the Python backend: the existing FastAPI/pandas cleaning engine still needs a separate running HTTPS server. No paid Cloudflare databases, storage, or containers are provisioned.

## Build and verify

From the repository root:

```sh
CLOUDFLARE_EXPORT=1 npm run build --prefix frontend
node --test deploy/cloudflare/worker.test.mjs
npm exec --yes --package=wrangler@4.11.1 -- wrangler deploy --config deploy/cloudflare/wrangler.jsonc --dry-run
```

Static output is in `frontend/out/` and is ignored by Git. Normal builds, Docker Compose, and local Next.js development keep their existing API rewrites; only `CLOUDFLARE_EXPORT=1` uses the exported asset build. Do not run normal `next start` directly on the exported build; rebuild normally first.

## Publish prerequisites

- A Cloudflare account must authorize deployment through `CLOUDFLARE_API_TOKEN`, with account Workers Scripts Edit access and any additional account-read permissions required by the CLI. Select the intended account; do not assume a default account when several exist.
- Supply `CLOUDFLARE_ACCOUNT_ID` for the selected account if required by Wrangler.
- Supply an actual backend HTTPS origin as `BACKEND_ORIGIN`. Set that backend's `CORS_ORIGINS` to the Cloudflare app's HTTPS origin and enable `COOKIE_SECURE=true`.
- The token belongs in secure environment settings, not this repository or chat. The saved Codex requirement scopes it to `api.cloudflare.com`. It must be saved/published and observed ready before remote deployment.

After those prerequisites are connected, publish with:

```sh
npm exec --yes --package=wrangler@4.11.1 -- wrangler deploy --config deploy/cloudflare/wrangler.jsonc --var BACKEND_ORIGIN:https://YOUR-BACKEND-HOST
```

Wrangler returns the real `workers.dev` URL after a successful publication. Do not substitute an invented URL or treat a dry-run as a deployment. Verify that the account uses the intended free plan and check current provider quotas before publishing.

The worker serves assets through ASSETS and forwards only `/api/` requests to the configured HTTPS backend. It preserves method/body/session cookies and response cookies, prevents cross-origin modifications, disables API caching, and returns a clear 503 when the backend is unconfigured. Uploaded spreadsheets are sent only to the explicitly configured cleaning backend. Uploads/jobs remain subject to that server's storage and availability limits.

Live acceptance checks: load the returned frontend URL, check its proxied health response, upload a synthetic CSV/XLSX, preview and confirm an interactive fix, download the corrected file/report, verify original/session isolation, and delete the test upload. Publishing only the frontend without a backend does not provide functional spreadsheet cleaning.

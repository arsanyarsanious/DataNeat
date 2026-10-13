# Render demo deployment

Use two Docker web services, selecting Render's Free tier if it is available in the account. Do not provision paid services, disks, or databases for this demo. Verify the current account pricing in Render before provisioning: access to render.com documentation was blocked from the preparation environment, so live pricing/quotas were not independently verified.

Repository: https://github.com/arsanyarsanious/DataNeat
Branch: main

## Backend

- Runtime: Docker
- Root directory: backend
- Dockerfile: Dockerfile (relative to root directory)
- Docker context: . (relative to root directory)
- Health check: /api/health
- Environment: PORT=8000, COOKIE_SECURE=true, MAX_UPLOAD_MB=5
- Set CORS_ORIGINS to the exact HTTPS frontend origin after the frontend URL is allocated, without a trailing slash.
- Run the existing single-worker Docker command. Keep ephemeral storage for this free demo; uploads and in-memory jobs can disappear after a restart or instance recycle.

## Frontend

- Runtime: Docker
- Root directory: frontend
- Dockerfile: Dockerfile (relative to root directory)
- Docker context: . (relative to root directory)
- Environment/build argument: API_INTERNAL_URL=<actual HTTPS backend URL, without trailing slash>
- The existing Dockerfile reads API_INTERNAL_URL during the build. Ensure it is supplied as a build argument, not solely after the image has been built. Rebuild whenever the backend URL changes.
- Next.js listens on Render's PORT environment variable. Keep API calls routed through Next's same-origin /api proxy so session cookies and private uploads work.

After both service URLs are known, update backend CORS_ORIGINS to the frontend HTTPS origin and redeploy it. Enable automatic deployments from main once the services work.

## Required account connection

Create/sign in to Render using GitHub and authorize repository access. Add a Render API key securely as RENDER_API_KEY in the Codex environment settings; do not paste it into chat or commit it. The saved requirement scopes proxy use to api.render.com. The deployment agent can then inspect the account and provision only the requested free services. Provider API access must be verified after the credential is supplied.

## Deployment acceptance checks

1. Backend HTTPS /api/health returns OK.
2. Frontend HTTPS /api/health returns OK through Next's proxy.
3. Upload a synthetic CSV/XLSX using the frontend, verify the session cookie, and open the interactive sheet.
4. Preview a highlighted issue fix, confirm it, and check that the value changes and the original remains intact.
5. Download CSV/XLSX and the report, then delete the test upload.
6. Confirm both services use the Free plan and no paid disk/database was created.

This is a demo configuration, not production hosting for confidential datasets. Free services can sleep when idle, share monthly usage allowances, and have ephemeral storage. Exact current restrictions must be confirmed in the provider dashboard. A public frontend URL exists only after the actual deployment succeeds; the Codex cloud localhost URLs are not public hosting.

## Backend for the published Cloudflare frontend

The root `render.yaml` now describes a Free Docker backend with secure cookies, a 5 MB upload cap, and CORS for `https://dataneat.dataneat-9df71239.workers.dev`. It is a prepared blueprint, not an already created Render service. Once the backend's real HTTPS URL is allocated and its deployment is live, update the Cloudflare Worker with `BACKEND_ORIGIN` set to that origin and redeploy. Verify health, upload, cleaning, and download through the Cloudflare frontend. The network draft includes the frontend hostname for those live checks.

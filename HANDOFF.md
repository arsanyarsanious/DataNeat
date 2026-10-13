# DataNeat — continue in another chat

## Project and source

- Repository: https://github.com/arsanyarsanious/DataNeat
- Branch: main
- This package contains the complete tracked application source, tests, lockfiles, sample spreadsheets, Dockerfiles, and deployment configuration. It intentionally excludes API keys, .env secrets, user uploads, dependencies, virtual environments, generated builds, and Git history.
- Start by reading README.md and VALIDATION.md. Read frontend/AGENTS.md and the installed Next.js documentation before frontend changes.

## Current website status

Frontend published at https://dataneat.dataneat-9df71239.workers.dev .

The public deployment is **frontend only**. The Python backend is not yet hosted/connected, and the Worker returns HTTP 503 for /api requests without BACKEND_ORIGIN. Do not claim spreadsheet cleaning works online until the backend is deployed and end-to-end checks pass.

The latest unfinished deployment work is to create the Python backend using the Free Render blueprint in render.yaml, obtain its real HTTPS origin, and redeploy the Cloudflare Worker with BACKEND_ORIGIN. The blueprint already enables secure cookies, sets a 5 MB upload cap, and permits the published Cloudflare origin through CORS. See deploy/RENDER.md and deploy/cloudflare/README.md.

Cloudflare access was verified in the previous chat and used for publication. A RENDER_API_KEY requirement was added to the previous cloud environment. Credentials are NOT included here and may not carry into a new chat/account. Check current configured credential readiness before requesting anything. Never print keys or ask for them in chat. Only free hosting has been requested; do not create paid services, disks, or databases without new authorization.

## Run on Windows

1. Install/open Docker Desktop and wait for the engine to run.
2. Open this extracted project folder in File Explorer. Click its address bar, type powershell, and press Enter.
3. Run:

```powershell
docker compose up --build -d
```

4. Open http://localhost:3000 . Docker Desktop must remain running. Local backend port is 8000; frontend port is 3000. Closing PowerShell is safe with -d.

A ZIP extraction is not a Git repository. If you want Git history and git pull updates, create a separate clone instead of overwriting this folder:

```powershell
Set-Location ([Environment]::GetFolderPath('Desktop'))
git clone https://github.com/arsanyarsanious/DataNeat.git DataNeat-Git
```

If that folder already exists, Git will refuse the clone; choose a new folder name. Do not delete or overwrite another working copy.

## Implemented features

Next.js/React frontend, FastAPI/pandas backend, private session uploads, CSV/XLSX import/export, profiling/type detection, invalid and ambiguous date review, grouped issue analysis/sorting, select-all cleaning plans, currency/percentage/unit/phone format choices, optional missing-data imputation, readable typography, privacy information, and interactive colored spreadsheet issue panels with preview/confirmation.

Interactive mode first cleans a separate copy conservatively, then highlights remaining supported issues. Hover/click/focus a cell, choose a cell/column fix, preview, and explicitly confirm. Originals remain intact; stale revisions are rejected. Advanced imputation remains in the cleaning-plan workflow. KNN and regression are deferred optional methods.

## Architecture and verification

- backend/app/main.py: session-scoped upload, profile, cleaning jobs, preview/export and interactive editor APIs.
- backend/app/core/: modular profiling, transformations, imputation, validation and interactive issue handling.
- frontend/app/page.tsx and frontend/components/: upload/analysis/plan/results and interactive spreadsheet UI.
- deploy/cloudflare/: static exported frontend assets plus same-origin API gateway; it does not run the Python backend.
- Backend data is stored privately in storage and expires after 24 hours. Jobs are in memory. Use one backend worker. Free-host ephemeral storage/restarts can lose files and jobs.
- Latest functional validation: 132 backend tests, 13 browser workflows, production build/TypeScript checks passed. Cloudflare gateway has 3 passing tests and a successful static export/dry-run. Public publication was confirmed through Cloudflare's API; direct public page checks were initially blocked by cloud network policy.
- Run backend tests with .venv/bin/python -m pytest -q after installing backend/requirements.lock.txt into a virtual environment.
- Frontend: npm ci --prefix frontend; npm run build --prefix frontend; npm run test:e2e --prefix frontend. Browser tests require the services and a Playwright-compatible Chromium.
- Cloudflare: CLOUDFLARE_EXPORT=1 enables static export; ordinary Next.js/Docker builds keep their normal API proxy. See the deployment guide for platform-specific commands.

## Suggested opening message for the next chat

"Continue working on my DataNeat project. Read HANDOFF.md, README.md and VALIDATION.md first. The complete source is in this ZIP or GitHub arsanyarsanious/DataNeat on main. The Cloudflare frontend is published, but the Python backend still needs free deployment and connection. Preserve existing files and features, check available credentials securely, and verify upload/cleaning/download before claiming the online app is operational."

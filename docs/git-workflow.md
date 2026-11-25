# DataNeat Git workflow

- Repository: `https://github.com/arsanyarsanious/DataNeat`
- Canonical branch: `main`
- Working copy: `C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable`

## Access

Git authentication is handled by the Windows credential manager for the
`arsanyarsanious` GitHub account. No token, password, or credential file is
stored in this repository or in the application config.

## Before every push

```powershell
# Backend
$env:PYTHONPATH="$PWD\backend"
python -m pytest backend/tests -q -p no:cacheprovider

# Frontend
cd frontend
pnpm exec tsc --noEmit
$env:CLOUDFLARE_EXPORT='1'
pnpm run build
```

Commit only source, tests, docs and required binary assets (such as the bundled
Inter font). `.env`, `frontend/out`, `node_modules`, local databases, uploads and
logs are ignored by `.gitignore`.

## Flow

```powershell
git status
git add -A
git commit -m "Clear, scoped description of the change"
git push origin main
```

**Documentation rule:** every app change must update `AGENT_BRIEF.md` plus the
relevant Markdown (`README.md`, `PROJECT_CONTEXT.md`, feature docs under
`docs/`) in the same commit. The brief is the canonical handoff; do not let it
fall behind the code.

Use a short-lived branch and a pull request for risky or collaborative work.
Deployment is separate from committing: the hosted build is uploaded only after
the local build and browser checks pass.

## History note

The portable workspace was merged into the established GitHub history on
2026-11-24. Both the existing `main` commits and the newer premium UI, upload
reliability and correction-menu work are preserved. A UTF-8 repair commit fixed
currency/symbol characters that arrived corrupted from an earlier upstream
commit.

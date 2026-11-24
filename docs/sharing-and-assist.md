# Read-only review links and the optional assistant

Two reviewed features added on 2026-11-23. Neither one changes the cleaning
engine, the original-upload preservation rule, the revision check, or the
audit/undo path.

## Read-only review links

A signed-in owner can create one expiring link for a file:

- `POST /api/files/{id}/share?ttl_hours=168` (owner session only) returns a
  bearer token. The token is an HMAC-SHA256 signature over
  `{version, file id, share epoch, expiry}`; it is not a session cookie.
- `GET /api/files/{id}/share` reports whether a link exists and when it expires.
- `DELETE /api/files/{id}/share` rotates the file's share epoch, which
  invalidates every previously issued link.
- `GET /api/share/{token}` returns read-only metadata: file name, revision,
  row/column counts, recorded step summaries, issue overview, and a 25-row
  preview.
- `GET /api/share/{token}/report` streams the existing PDF report.

The public routes are the only `/api` paths that bypass the sign-in check. They
are GET-only, rate-limited by the existing middleware, and never expose editing,
deletion, the original bytes, the owner's session, or the workspace's change
history. A token stops working when it expires, when the owner revokes it, when
the file is deleted, or when a temporary file reaches its retention limit.

Signing key: `SHARE_SIGNING_KEY` when set, otherwise `STORAGE_SIGNING_KEY`,
otherwise a private `.share-key` file beside `STORAGE_DIR` (mode 0600, never in
source control).

## Optional bring-your-own-key assistant

`POST /api/assist` is opt-in and suggest-only. The browser sends the user's
provider, model, key, a consent flag, and one file id plus column name.

- The server extracts up to twelve short sample values from the current working
  copy; it never accepts sample values from the client.
- The request is forwarded to a fixed OpenAI-compatible provider preset
  (`gemini`, `groq`, `openrouter`); arbitrary base URLs are not accepted, which
  prevents server-side request forgery.
- The key is used for that request only: it is not stored, echoed, or logged.
- `suggest_type` output is validated against the engine's column-type
  vocabulary; `explain` output is plain text. Applying a suggested type reuses
  the existing `rules` decision, so it is previewed, recorded, and undoable.
- `AI_ASSIST_ENABLED=false` disables the endpoint entirely.
- The assistant is never part of the automatic cleaning questionnaire and is
  never applied without user confirmation.

## Environment switches

| Variable | Purpose |
|---|---|
| `SHARE_SIGNING_KEY` | Optional explicit share-token signing key |
| `AI_ASSIST_ENABLED` | `false` disables the assistant server-side |
| `MAX_WORKFLOW_CELLS` | Rows x columns analysis budget; `0` disables |
| `MAX_STORAGE_MB` | Total stored-snapshot byte budget; `0` disables |

## Hosted-beta notes

- The static export must include `app/share/page.tsx` (`/share`); the backend
  public route and the page are deployed together.
- PythonAnywhere free accounts allow outbound HTTP only to whitelisted hosts.
  To use the assistant on that host, add `api.groq.com`,
  `generativelanguage.googleapis.com`, and/or `openrouter.ai` in the
  PythonAnywhere whitelist UI. The assistant fails with a clear retry message
  until a provider host is allowed.
- The guest sees the values rendered in the 25-row preview and the PDF. Share
  links are bearer secrets; the owner warning says so.

## Verification

- `backend/tests/test_sharing.py`: token creation, ownership, tampering,
  expiry, revocation, deletion, read-only access, private key file.
- `backend/tests/test_ai_assist.py`: consent, server kill switch, provider
  errors, validation, sample bounds, ownership, no key echo.
- `backend/tests/test_workflow_budget.py`: analysis and storage budgets.
- Full backend suite: 711 passed. Frontend production build, static export, and
  TypeScript checks passed.

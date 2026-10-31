# Free public beta deployment

Use the root Dockerfile: the exported Next.js frontend and Python API share one
Render Free web service and one HTTPS origin. No Node server, paid disk, or second
Render service is required. Use one process and one workflow worker.

Apply deploy/supabase-storage.sql in the existing Supabase project. It creates
only app-specific file storage objects. RLS is enabled and all browser-role
privileges are revoked: snapshots can be accessed only by the backend service
credential. Verified account/session ownership is enforced by the API.

Set the environment variables documented in render.yaml. Never commit secret
values. STORAGE_SIGNING_KEY authenticates snapshots before deserialization; keep
a private backup and do not rotate it without migrating stored snapshots.
SUPABASE_SERVICE_ROLE_KEY must remain backend-only and must never be supplied as
a NEXT_PUBLIC variable. Do not upload local user files or local .env files.

Storage commits are atomic in Supabase and must succeed before an API action is
reported successful. Render local files are a read-through cache. Saved files
have no automatic expiry; temporary files expire after 24 hours. Cleaning jobs
in progress may need retrying after a restart; the latest committed state can be
reopened from My files. Downloaded backups are still recommended.

Free beta caps: 2 MB/upload, 10,000 rows, 50 columns; at most 20 active files and
20 MB of encoded snapshots per account, 10 MB per snapshot and 150 MB globally.
The API additionally limits saved files by the original/history byte count. These
limits are deliberately below free provider quotas. No payment flows are active.

Render's built-in RENDER_EXTERNAL_URL is added to allowed origins. Add the exact
new HTTPS login redirect to Supabase Auth URL configuration, retaining local
redirects. Verify Google audience restrictions before announcing general access.

Validation: production Docker build, backend tests, public routes, unauthenticated
API rejection, signed-in upload/clean/download, then saved-file recovery after a
fresh instance with empty local storage. Confirm Free is selected. No card is
needed for this intended setup; stop if Render requires a paid plan.

Provider limits: https://render.com/docs/free and https://supabase.com/pricing.
Render sleeps after inactivity; first load can take approximately one minute.
This is a public testing beta, not an availability or backup guarantee.

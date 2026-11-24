# Sign-in and usage monitoring

Google and email/password sign-in use Supabase Auth. Only a Free organization/project is authorized. Do not add a payment card, enable a paid plan, enable billing in Google Cloud, buy a domain, or add paid services for this setup.

## Current behavior

The responsive `/login` page contains both methods, registration, and password recovery. Without provider configuration it clearly shows setup pending and does not accept credentials. The existing workspace remains available behind the private ChatGPT Sites access policy. Once either Supabase environment setting is supplied, backend data APIs require authentication; an incomplete/invalid configuration fails closed.

## Activation

1. Connect the Supabase account and select an existing Free project, or create a Free project in a Free organization. Verify that no card is required before proceeding.
2. Keep email confirmation enabled. Configure an email sender that has a permanent free, no-card plan before opening email registration beyond the project team. Supabase's default mail sender is for testing and is not a general-purpose production sender.
3. Set the Supabase Site URL to `https://dataneat-workspace.alertpeach16.chatgpt.site` and allow the exact callback URLs `/login` and `/login?recovery=1` on that origin. Allow local development callbacks only when needed.
4. In Google Auth Platform, create an OAuth web client without enabling paid services or billing. Configure the Supabase-provided callback URL, enable Google in Supabase, and complete the applicable consent-screen setup. Never paste client secrets into chat or source.
5. Configure the backend's `SUPABASE_URL` and browser-safe `SUPABASE_PUBLISHABLE_KEY`. Do not use a service-role or secret API key. Set `GOOGLE_SIGN_IN_ENABLED=true` only after the provider works. Set `ADMIN_EMAILS` to explicitly approved, verified administrator emails; no first-user admin promotion is used.
6. Recreate Docker services after environment changes. The Sites Worker forwards only the required DataNeat session/authentication cookies through the protected tunnel. Preserve the Site's existing audience.
7. Verify real email verification, email sign-in, Google sign-in, recovery, logout, access denial when signed out, two-account upload isolation, and admin-only monitoring before claiming sign-in is live.

## Storage and monitoring

Provider passwords are handled by Supabase, never stored by DataNeat. The backend verifies access tokens against the configured provider and sets an HttpOnly session cookie. Provider sessions are managed by the Supabase browser SDK with PKCE. Upload access includes the verified provider user ID plus the browser session ID.

Usage is stored in `usage.sqlite3` inside the existing private Docker storage volume. It contains account ID/email and timestamps/event names for sign-ins, uploads, cleaning requests, editor opens, confirmed fixes, and downloads. It excludes spreadsheet contents, cell corrections, filenames, and passwords. Usage records expire after 90 days. Only the server-enforced administrator allowlist can read `/api/admin/usage`; an authenticated administrator sees a Usage overview control.

The current no-card tunnel depends on the computer, Docker and gateway running. Temporary tunnel hostnames can expire or change and must be updated in Sites configuration when renewed.

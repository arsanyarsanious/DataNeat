# Google accounts and saved files

## Current status

The local installation now has verified Google accounts through Supabase, an account file library, and explicit temporary versus saved retention. Authentication and Google are enabled, and the owner completed a live Google sign-in and saved/reopened a cleaned workspace on October 28, 2026. No demonstration identity or authentication bypass is shipped.

The owner explicitly chose to keep Google in **External / Testing** for now. Only allowed test accounts can sign in; the owner's account is already listed. A public application URL and privacy page are not yet available, so public Google publishing has been deferred. Do not recreate the projects or replace real branding with placeholder URLs. Google requires home/privacy links for external production apps and ownership verification for the app's domain: [Google branding requirements](https://support.google.com/cloud/answer/15549049?hl=en-GB), [production readiness](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance).

Current Supabase project: `https://vdhznrecrwwegdomshva.supabase.co`. Google Cloud project: `dataneat`. OAuth client: `DataNeat Web`. The approved local origin and callbacks are documented below; secret values are deliberately excluded. The requested private credentials backup is in the owner's `Documents/Codex/private/DataNeat-account-keys.txt`.

## Connect authentication

1. Create or select the owner's Supabase project. Get its HTTPS project URL and **publishable** key from the project dashboard. The existing application also accepts a legacy public anon key. Never use a service-role key.
2. In Google Auth Platform, configure the application's branding, audience, and a Web application OAuth client. Use only identity scopes (openid, email, profile). Add the app's origin, initially `http://localhost:3000`, to the client's authorized JavaScript origins. Use the exact Supabase callback URL shown in its Google provider settings as the authorized redirect URI.
3. Enter the Google client ID and secret into Supabase's Google provider settings and enable that provider. Google secrets belong there, not in frontend code or the DataNeat environment file.
4. In Supabase Authentication URL Configuration, set the Site URL and permit the login callback. For local testing, `http://localhost:3000/login**` allows the application's return-path and recovery query parameters. For deployment, allow only the actual HTTPS origin and required login callback patterns. The app validates return destinations to `/files`, `/workspace`, or a workspace file UUID.
5. Set these existing environment variables in the local `.env` or deployment secret settings:

   ```dotenv
   SUPABASE_URL=https://YOUR_PROJECT.supabase.co
   SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLIC_PUBLISHABLE_KEY
   GOOGLE_SIGN_IN_ENABLED=true
   ```

6. Recreate the backend service to load the variables. For a public HTTPS deployment, also set the exact `CORS_ORIGINS` and `COOKIE_SECURE=true`. Keep the cover page first: Begin cleaning → login → workspace.
7. Test with an allowed real Google account. In Google testing mode, add the intended test accounts to its audience. Check sign-in, refresh, sign-out, and another account's isolation. Production availability depends on the provider's audience and verification configuration.

Provider instructions: [Supabase Google sign-in](https://supabase.com/docs/guides/auth/social-sign-in/auth-google), [Supabase redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls).

## What users can save

- An upload starts as a temporary file with a 24-hour expiry. Saving is an explicit **Save to my files** action after signing in.
- Saving preserves the uploaded original, current table, settings, accepted findings, and cleaning history. Later confirmed changes update the saved workspace automatically.
- **My files** lists only the verified account's saved workspaces. Users can search, rename, reopen, or permanently delete them. A saved workspace has no automatic expiry.
- **Make temporary** requires confirmation, removes the file from My files, and starts a new 24-hour period from that choice.
- Opening a new spreadsheet preserves saved work. Deleting a saved workspace requires explicit confirmation.
- Existing anonymous local uploads are not silently claimed when accounts are first enabled. Export or re-upload those temporary files after signing in.

## Where data is stored

Supabase supplies identity verification. Spreadsheet workspaces are stored on **the DataNeat server**, in the existing persistent Docker volume `dataneat-storage`; they are not uploaded to Google Drive or Supabase Storage by this feature. Google sign-in does not authorize access to Drive.

Default account admission limits are 100 saved files and 1,024 MB, including original data and history. Configure `MAX_ACCOUNT_FILES`, `MAX_ACCOUNT_STORAGE_MB`, and the overall record limit `MAX_STORED_FILES` for the host. The account page shows current usage. Existing saved work remains editable even if later history increases its size beyond the admission quota.

A persistent volume is essential on a hosted server. Rebuilding/restarting the container preserves it; deleting the volume or losing the host's disk does not. Back up the server's storage for durable hosting. Browser recipes and view preferences remain browser-local.

## Verification boundary

Automated tests exercise verified identities via test doubles, account isolation, same-account access from another browser session, retention over 24 hours and service restart, quota errors, stale cleaning-job snapshots, and deletion. Separately, live owner testing verified Google authentication, real-account file saving, corrected data/history/original retention, rename, and reopening after starting a new spreadsheet. This verifies the current local testing setup; it does not imply public hosting or a published Google production application.

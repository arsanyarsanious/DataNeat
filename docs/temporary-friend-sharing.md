# Temporarily share DataNeat with a friend

`http://localhost:3000` works on the computer running DataNeat. On your friend's computer, `localhost` refers to their own computer. A temporary tunnel can give them an HTTPS link to your running copy.

This is a setup guide only. No public tunnel has been started, no hosting has been deployed, and no authentication or environment settings have been changed for sharing.

## Start a temporary preview

1. Keep your PC awake, connected to the internet, and running Docker and DataNeat. Check that `http://localhost:3000` opens locally. Install Cloudflare's `cloudflared` first if needed, using its [official download instructions](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

2. Open a terminal on this PC and run:

   ```powershell
   cloudflared tunnel --url http://localhost:3000
   ```

   Copy the generated `https://…trycloudflare.com` address. It is temporary, changes with each new tunnel, and stops working when the tunnel stops. Keep the PC, Docker, and this process running while your friend tests. This is intended for testing; it is not a stable website address or a production deployment. [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

3. Add that exact HTTPS origin to the existing `CORS_ORIGINS` entry in the project's `.env`. Preserve `http://localhost:3000` and any other existing allowed origins. Use commas without spaces and no trailing slash. Example placeholders:

   ```dotenv
   CORS_ORIGINS=http://localhost:3000,https://YOUR-TUNNEL.trycloudflare.com
   ```

   The backend also checks this list before uploads and cleaning changes. Recreate only the backend to load the updated setting, from the project directory:

   ```powershell
   docker compose -p dataneat up -d --no-deps --force-recreate backend
   ```

4. In **Supabase → Authentication → URL Configuration → Redirect URLs**, add:

   ```text
   https://YOUR-TUNNEL.trycloudflare.com/login**
   ```

   Replace the hostname with the actual generated hostname. DataNeat currently returns to `/login?next=…`; the narrowly scoped `/login**` pattern accommodates those query parameters. Keep the existing localhost redirects and Site URL. Do not allow every `trycloudflare.com` hostname. [Supabase redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)

5. The current Google application is **External / Testing**, with the owner's account listed. For your friend's Google account, open the existing `dataneat` project in **Google Auth Platform → Audience → Test users → Add users**, add their email, and save. [Google test-user setup](https://developers.google.com/workspace/guides/configure-oauth-consent)

   Keep the existing Google client and Supabase provider credentials. Do not replace Google's authorized Supabase callback URL with the tunnel URL: Google's callback remains the project's Supabase `/auth/v1/callback`; the temporary DataNeat login return belongs in Supabase's redirect list. [Supabase Google sign-in](https://supabase.com/docs/guides/auth/social-sign-in/auth-google)

6. Open the public link yourself and verify **Begin cleaning → Google sign-in → upload → cleaning → download**. Then send your friend that link; they should sign in with their own permitted test account. A tunnel link alone does not add them to Google's test audience.

## End the session

Press **Ctrl+C** in the tunnel terminal. The public address immediately becomes unavailable. Remove the obsolete tunnel origin from `CORS_ORIGINS`, recreate the backend again, and remove its Supabase redirect entry. Keep localhost entries. Each future tunnel needs its new hostname added before sharing.

Anyone who obtains the temporary address can reach DataNeat's public pages; account access still uses the application's sign-in rules. Share the preview only with the intended tester. A permanent URL that works while this PC is off requires hosting DataNeat separately and completing the public Google authentication setup.

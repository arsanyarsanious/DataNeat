# Excel on the web — testing the DataNeat add-in

Excel on the web supports developer sideloading, but modern Chrome/Edge may
block a public Office page from loading `https://localhost`. The preview
therefore includes a temporary Cloudflare quick-tunnel path.

## Prerequisites

- A Microsoft account that can open [Excel on the web](https://www.office.com/launch/excel).
  A school/work account may also have an Office web plan.
- The DataNeat companion prepared on this machine (`.venv`/certificate from
  `companion/setup.ps1`).

## Steps

### 1. Start the local companion

Open PowerShell window 1:

```powershell
cd "C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable\excel-addin"
.\companion\run.ps1
```

Leave it running. It serves `https://localhost:9443`.

### 2. Create a temporary public HTTPS tunnel

Open PowerShell window 2:

```powershell
cd "C:\Users\Arsany Arsanious\Desktop\DataNeat-Portable\excel-addin"
.\companion\web-tunnel.ps1
```

The script:
- downloads `cloudflared` once (if needed),
- reads the persistent add-in token created by `run.ps1`,
- starts a temporary `*.trycloudflare.com` tunnel,
- generates `generated/manifest.web.xml` with a tokenized task-pane URL,
- prints the public task-pane base URL and manifest path.

Keep both windows open. The tunnel URL changes every run; the token persists
until you delete `generated/addin-token.txt` and restart the companion.

### 3. Open Excel on the web and sideload

1. Open [Excel on the web](https://www.office.com/launch/excel) in Edge or
   Chrome, using the account with Excel access.
2. Create or open a workbook; put column headers in row 1.
3. Go to **Home → Add-ins → More Settings** (or **Insert → Add-ins**).
4. Choose **Upload My Add-in** and select:
   `excel-addin\generated\manifest.web.xml`
5. Open **DataNeat** from the add-in list.

### 4. Test

- Click **Analyze active sheet**.
- Review the metrics and per-column findings.
- Click **Highlight issues**; then **Clear highlights**.

The web task pane sends the sheet snapshot as JSON
(`POST /api/addin/analyze-json`) rather than multipart FormData. Excel on the
web rejected the multipart request with “There was an error parsing the body”;
the JSON path avoids that host quirk. The desktop multipart endpoint remains.

Highlighting on Excel web is batched: original-fill backup, fill application,
and clear/restore use 200 ranges per Office.js sync. This avoids Office’s
request-payload limit on sheets with thousands of flagged cells.

The companion now requires the launch token on `/api/addin/*`. The token is in
the generated manifest URL and is sent as `X-Addin-Token`; the broad
`*.trycloudflare.com` CORS rule was replaced by a same-origin check. Loading the
task pane without the token lets the page render, but Analyze returns 401.

The web build detects Excel Online and uses smaller read batches, a 1,000,000
cell limit and a 5,000 highlighted-cell cap. Desktop remains 3M cells / 10k
highlights.

## If it does not load

- Open the printed public task-pane URL directly in the same browser first; it
  must return the DataNeat task pane.
- Re-upload the newest generated manifest after restarting the tunnel; an old
  URL will no longer work.
- If Excel says it cannot access the manifest, verify the tunnel window is
  still open and the URL from its output matches the generated manifest.
- If the add-in loads but the task pane is blank, open the public task-pane URL
  directly; the tunnel may have expired.
- If you see “There was an error parsing the body”, the task pane is stale:
  close and reopen the add-in (or reload the Excel tab) so it fetches the JSON
  task-pane code, then retry Analyze.
- If you see “The request payload size has exceeded the limit”, the task pane
  is stale (old one-sync highlighting). Close/reopen the add-in to load the
  batched highlighter and retry.
- If you see “Add-in access token is missing or invalid”, re-upload the newest
  generated manifest, close and reopen the task pane, and retry. The token is
  stored in `excel-addin/generated/addin-token.txt`.
- If Excel web still blocks the tunnel, use a licensed desktop Excel or the
  browser mock (`/taskpane.html?mock=1&token=...`) to continue UI/engine testing.

## Security

The quick tunnel is temporary and the API requires the generated add-in token,
but the task pane and manifest URL are still reachable by anyone who has them.
Use it only for temporary testing, do not share the URL or generated manifests,
and press **Ctrl+C** in the tunnel window when finished. The token is persisted
locally in `generated/addin-token.txt`; delete it and restart to rotate.

The quick tunnel sends traffic through Cloudflare; the sheet data is processed
by the local engine, but the task-pane/API traffic traverses the tunnel. Do not
use this path with confidential production data.

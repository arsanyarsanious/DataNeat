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
- starts a temporary `*.trycloudflare.com` tunnel,
- generates `generated/manifest.web.xml` pointing at that tunnel,
- prints the public task-pane URL and manifest path.

Keep both windows open. The tunnel URL changes every run.

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
- If Excel web still blocks the tunnel, use a licensed desktop Excel or the
  browser mock (`/taskpane.html?mock=1`) to continue UI/engine testing.

## Security

The quick tunnel exposes the local companion to the internet for as long as it
runs. The companion has no login in this preview and can analyze uploaded sheet
data on your machine. Use it only for temporary testing, do not share the URL,
and press **Ctrl+C** in the tunnel window when finished.

The quick tunnel sends traffic through Cloudflare; the sheet data is processed
by the local engine, but the task-pane/API traffic traverses the tunnel. Do not
use this path with confidential production data.

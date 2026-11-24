# DataNeat for Excel — Tier L preview

This is the first **runnable, read-only** Excel add-in milestone:

- Local companion app runs the existing DataNeat engine.
- Office.js task pane reads the active sheet (up to **3,000,000 cells**).
- Issues are highlighted in the workbook.
- Highlights can be cleared and original fills restored where Excel settings
  could store them.
- No values are changed; imputation and automatic cleaning are not part of this
  preview.

## Requirements

- Windows 10/11, 64-bit
- Microsoft 365 Excel desktop (or Excel 2019+ with Office.js support)
- Python 3.12 64-bit (only needed for this preview; a packaged installer will
  replace it in a later phase)
- Internet access for the Office.js runtime

## 1. Set up the companion

```powershell
cd excel-addin
.\companion\setup.ps1
```

This creates `.venv`, installs the engine dependencies, generates a localhost
certificate and trusts it for your Windows user.

## 2. Start the companion

```powershell
.\companion\run.ps1
```

Leave the window open. It serves:

- task pane: `https://localhost:9443/taskpane.html`
- local API: `https://localhost:9443/api/...`

You can test the interface in a browser first:

`https://localhost:9443/taskpane.html?mock=1`

## 3. Sideload the add-in in Excel

1. Open Excel desktop.
2. **Insert → Get Add-ins → My Add-ins → Upload My Add-in** (the exact path
   varies slightly by Excel version).
3. Choose `excel-addin/manifest.xml`.
4. In the **Home** ribbon, open the **DataNeat** add-in/task pane.

If Excel opens the workbook in **Protected View** or as read-only, click
**Enable Editing** first. Excel blocks all add-in writes in those modes, so the
analysis may work while highlighting is refused. A licensed/signed-in Excel is
required for Office.js formatting on some installations.

## 4. Use it

1. Open a worksheet whose first row contains column names.
2. Click **Analyze active sheet**.
3. Review the row/column/issue summary and the per-column findings.
4. Click **Highlight issues** to paint flagged cells.
5. Click **Clear highlights** to restore the previous fills.

For the first test, use a copy of a workbook. The preview is read-only, but it
does write cell fill colors for highlighting.

## Current limits (Tier L preview)

- Up to 3,000,000 cells.
- First row treated as headers by default.
- Cell highlighting capped at 10,000 cells per run; column totals are complete.
- Excel reads displayed cell text, so date/number display formatting affects
  what is analyzed.
- Excel settings have a size limit; if the original-fill backup cannot be
  stored, clearing removes the highlight fills instead of restoring them.
- Excel may block add-in writes when the workbook is in Protected View or when
  the Office installation is unlicensed/signed out. Enable editing and sign in
  before highlighting.
- No automatic cleaning or corrections yet; this milestone proves local
  analysis and on-sheet issue highlighting.
- The companion must be running before the task pane is used.

## Files

- `manifest.xml` — sideload manifest
- `taskpane/` — Office.js task pane
- `companion/run.ps1` — starts the HTTPS local engine
- `companion/certs.py` — localhost certificate generation/trust

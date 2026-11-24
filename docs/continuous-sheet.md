# Continuous interactive sheet

The interactive spreadsheet has one continuous vertical scroll area. Pagination buttons and page numbers were removed from the sheet; the existing read-only API still serves bounded chunks internally. A 48px row window renders the visible area plus overscan and prefetches the next chunk. Cached chunks are bounded to twelve and are invalidated by file/revision/filter changes. Pending requests are aborted on invalidation or unmount, with retry for failed loads.

Search and issue navigation scroll to the original spreadsheet row in the same table. Corrections refresh the currently viewed region and invalidate old revision data. Filtering preserves original spreadsheet row labels. Header controls remain sticky; long cell values use ellipsis while correction controls retain full values. Browser Find only sees rendered cells, so whole-file lookup uses the Search button.

Validation: production build/TypeScript and synthetic large-file UI checks of bottom/top scrolling, bounded rendered rows, search jumps, corrections, and filters. No new runtime dependency or paid service.

Ctrl+F (or Cmd+F) in the cleaning view opens DataNeat's whole-file Search. Native browser Find cannot inspect rows that have not been rendered; the app search handles these and scrolls directly to each result. The current scroll region is retained on correction and the current internal chunk is saved for refresh.

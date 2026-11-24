# Progressive cleaning workspace

The post-upload flow has three views: choose a method, clean the current working copy, and review/export. Navigating between views never reuploads or resets the working copy. The view is retained per file in session storage and restored after refresh.

The cleaning view prioritizes the spreadsheet. Issues/filters, history/undo, tools, and help/legend open in one optional side panel at a time. Existing preparation, column rules, recipes, batch, review and export tools remain available under Tools. Text unification is accessible there, while column settings and issue finding remain in sheet headers.

Automatic cleaning remains optional. Pending missing-label decisions appear before the survey, with an explicit continuation option. Completed automatic-run exclusions are retained for the results explanation. Results provide collapsed change/remaining/unchanged summaries plus XLSX, CSV and PDF preparation and downloads. Users can return to the same sheet to continue cleaning or undo.

WorkflowTools stays mounted while hidden so background jobs and recovery keep working. Global progress and actionable errors remain visible; success messages dismiss after five seconds while audit history remains available.

Validation: production frontend build/TypeScript; synthetic-file browser checks of method choice, panel switching, automatic cleaning, results, refresh persistence, history/undo, and export. No new service or paid dependency was introduced.

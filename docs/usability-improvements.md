# Cleaning usability improvements

1. The working sheet offers Clean automatically and Clean manually with a one-line explanation.
2. A whole-file overview counts affected columns, distinct issue types, flagged cells and recorded steps. Issue type buttons navigate to representative cells.
3. A server-side affected-row view filters all pages by column and issue type while preserving original row indices. Clearing the filter restores the full sheet. Fix scopes always refer to the full dataset, never just the visible rows.
4. The cell editor exposes scope buttons with target counts. Manual replacement offers this cell, exact matching values, or the same issue in the selected column. Other actions expose supported cell/column scopes. Counts identify candidate cells; the existing preview calculation still reports actual changes.
5. The automatic survey shows examples from current column samples and explains date interpretation and numeric estimates.
6. Multiple applicable columns can share an exception in one action. Each resulting exception remains independently editable/removable.
7. Automatic cleaning reports cell changes and the number of cells with remaining flags, with Review remaining issues and Download cleaned file actions.
8. Undo last action and Undo automatic cleaning run use the audited replay engine. Run undo removes remaining steps from that run, replays independent later steps, and commits atomically. A dependency failure leaves the current revision unchanged. Run IDs survive single-step undo and refresh.
9. Optional survey answers are stored only in this browser after a successful run. Load saved choices validates settings against the new file, omits absent/incompatible exception columns and reports them before applying anything. No sampled values are stored in the preference record.

Existing originals, per-step history, background progress/cancellation, owner isolation, revision checks and export rules remain in place. Earlier automatic runs that predate run IDs retain per-step undo only.

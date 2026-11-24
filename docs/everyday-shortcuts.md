# Everyday usability shortcuts

- Search values across the current complete dataset, optionally restricted to a column; jump preserves original spreadsheet row numbers. Column-name jump is separate. Search is case-insensitive literal text, not regex, and never wraps silently.
- Before & after compares the preserved original upload to the current working copy, paginated at 50 cells. Removed rows and column renames are explicit. Undone changes disappear. Strings are quoted to expose spaces.
- “This value is correct” accepts one check for a cell, an exact value in the column, or the issue throughout the column. This never changes data and is audited/undoable. Other checks remain active.
- Tools / Ready-made shortcuts provides text trim + Title, trim alone, boolean labels, and unambiguous ISO dates. Users choose the column and apply explicitly. Existing plan jobs provide atomic execution, revision checks, progress and step history.
- A compact suggested-next-action points to an existing issue in the whole file and opens its correction. No action runs automatically.
- Correction forms display one actual dry-run before/after example as settings change. This adds no confirmation step.
- Success notices offer immediate undo; all steps remain in History after notices disappear.
- Leaving or starting a new spreadsheet warns when revisions have not been downloaded as CSV/XLSX or a task is running. Download clicks are recorded per-file/revision in session storage; PDF is not considered a data backup. Browsers control the wording of native unload warnings.

All functionality remains local; no new account, paid service or external transmission.

Interactive missing-value corrections now expose Forward fill, Backward fill, Linear interpolation for plain numeric measurements, and grouped mean/median/mode/directional fills. Group selection appears directly below correction settings. Ordered methods require a numeric or ISO date ordering column, plus grouping or explicit single-sequence confirmation. Ordering is ascending and does not rearrange the sheet; existing conservative interior-gap semantics remain. No leading/trailing extrapolation, overwriting observations, or crossing group boundaries. Currency/percentage interpolation is not advertised until amounts are normalized to plain numeric measurements. Existing imputation engine tests: 68 passing.

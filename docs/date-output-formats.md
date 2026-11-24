# Date output format

Date normalization accepts output_format: YYYY-MM-DD (default), DD/MM/YYYY, MM/DD/YYYY, YYYY/MM/DD, DD-MM-YYYY or MM-DD-YYYY. Input interpretation remains a separate preserve/day_first/month_first choice. Invalid or unresolved ambiguous inputs remain unchanged. Include time preserves the time and UTC offset when selected.

The cell tooltip, Column settings and Automatic cleaning survey expose the output format. Survey exceptions and saved choices support per-column output formats. Recipes and exports carry the selected values.

Workflow history records which rows were parsed successfully and their generated format. Subsequent normalization reads those rows with their known output order, preventing day/month swaps and repeat ambiguity flags. Later edits invalidate that row's format provenance; renames and undo replay preserve it correctly.

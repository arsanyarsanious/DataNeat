# Missing-value label review

In the interactive workflow, only actual nulls and blank strings are missing by default. Recognized text labels (NA, N/A, null, empty and the existing marker vocabulary, case-insensitive) are highlighted as possible missing-value labels and remain unchanged until the user chooses for that column.

The sheet banner and cell tooltip offer Convert labels to empty or Keep as text. Conversion is an audited, undoable column decision and enables the recognized labels as missing for later operations. Keep preserves strings and removes the pending-label question. Actual blanks remain missing in both cases. Unresolved columns are skipped by automatic cleaning, so imputation does not silently replace candidate labels. Column decisions can be transferred explicitly in recipes and follow column renames.

Opening an existing workflow refreshes annotations without changing its data or undoing earlier decisions. Labels already converted by prior confirmed cleaning are not reconstructed automatically; undo the relevant step to restore them.

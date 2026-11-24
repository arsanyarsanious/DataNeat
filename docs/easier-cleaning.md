# Faster, clearer cleaning

## Review suggested fixes

The recommended entry after upload, and the same toolbar button inside the sheet, open **Quick cleaning**. Common corrections are grouped by issue type across eligible columns: whitespace, boolean labels, unambiguous date formats, clock formats, durations and optional text capitalization. Full duplicate removal is a separate, unchecked group and runs last. Only whitespace is initially selected. Each group can use its chosen format across several columns; More options lets the user exclude columns.

The user selects fixes, requests one combined preview, then applies the reviewed set in one background plan. Changing a selection, format, columns or revision invalidates the preview. The preview and application report changed cells separately from removed rows. Each underlying action remains in History and supports the existing replay Undo.

Suggestions preserve inferred/declared identifiers, columns with accepted manual corrections, and unresolved missing-label columns. Invalid/ambiguous values, missing-value estimates, unusual values, semantic interpretations and relationship judgments require a separate user decision. No automatic startup cleanup has been added. Each combined review supports at most100 actions; additional actions are explained and can be reviewed in another run.

## One decision per issue and guided cleaning

Guided cleaning presents one column and issue kind at a time using whole-file counts. Fix this type opens the existing correction with an eligible bulk scope. Resolving its findings advances to the next type; partial corrections remain on the same type with updated counts. Skip and Next move the walkthrough, not the data or acceptance flags. Progress recovers in the same tab. The completion panel distinguishes reviewed, skipped and no-longer-flagged types, while still showing remaining issue groups.

Manual replacements additionally offer **More scope options → This issue in selected columns**. The user explicitly selects columns and previews the combined effect. Only cells annotated with the chosen issue type are replaced; unrelated cells/columns and protected identifiers are preserved. This scope works with a user-entered constant or explicit clearing. Individual audit columns and original rows remain exact, and Undo restores the prior copy. Row-dependent decisions are excluded from transferable recipes.

## Simpler corrections and saved choices

Cell correction panels show the suggested action, Before/After, required settings and scope. Alternate actions and detailed settings sit under More options; Change correction opens them. Matching-value and cross-column replacement scopes sit under More scope options. Required parameters, acknowledgements and visible blocking errors remain available before Apply. Boolean output labels can be chosen directly.

**Saved choices** stores up to20 named sets of transferable notation actions in this browser, each with up to100 actions. Storage contains column names and action settings, not cell values, row references, revision numbers, acceptance decisions, estimates, replacements or destructive duplicate removal. A current-file compatibility review skips absent/incompatible/protected columns. A fresh combined preview is always required before applying. Saved choices can be updated by name or deleted.

## Clear completion and website guide

The final screen says Ready to download only when no issue flags remain under current checks. Otherwise it says Your selected cleaning is complete and states how many flagged cells remain; review and export are still available. This does not certify all real-world values as correct.

The sidebar now includes **Website guide**, a public, searchable guide at `/guide` with15 anchored sections, examples, workflows and operating limits. It opens separately from an active cleaner to preserve the current file. Theme and collapsed navigation follow existing preferences. Existing manual/automatic cleaning and all four reviewed quality tools remain available.

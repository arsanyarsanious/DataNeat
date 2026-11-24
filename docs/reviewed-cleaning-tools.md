# Reviewed cleaning tools

These four tools run on the existing interactive working copy. Open **Tools → More cleaning tools**. A missing numeric cell also links to model imputation; relationship and outlier flags link back to their tool.

## Related column rules

Build up to 30 named rules: compare two numeric/date/text columns, check `Target = Left (+, −, ×, ÷) Right`, or require a target when another column equals/does not equal exact text. Numeric tolerance and ambiguous-date interpretation are explicit. Known date formats from earlier decisions are preserved.

Check a draft, then review and save it. Saving only adds issue flags, including exact target column and spreadsheet row. For an arithmetic rule, separately review recalculation of one row or all affected targets. Clearing flagged target values is another explicit correction. Invalid operands, division by zero and ambiguous dates cannot be guessed; recalculation skips them. A correction that introduces a conflict with another saved relationship is blocked. No arbitrary expression evaluation is used.

## KNN and Iterative imputation

Choose a plain numeric target with empty cells and 1–8 related plain numeric helper columns. Identifiers, literal missing labels, dates, booleans and unconverted labelled amounts are excluded. Observed target values are never overwritten. Previously estimated cells and user constants are excluded from model evidence.

The review computes deterministic held-out mean absolute error and a training-target median baseline. Fitting and scaling exclude the hidden test targets; random holdout does not establish future/time-series accuracy or guarantee the true missing values. If there are fewer than 10 target observations, validation is reported as unavailable. At least five original donors are needed (or the requested KNN neighbor count, if larger).

KNN uses robust scaling and distance-weighted neighbors. Iterative uses scikit-learn's explicitly enabled experimental IterativeImputer. Fitting uses at most 2,000 sampled original donors, up to 10,000 missing target cells per run, 8 helpers and transform batches of128. Cells without any usable original helper measurement stay empty. An estimate acknowledgement is required before applying. Dotted sheet underlines, audit metadata and the PDF report retain estimate provenance and validation results.

## Similar records

Select 2–5 matching fields, a similarity threshold and optionally an exact blocking column. Text is compared using local normalized spelling similarity; identifier/email/numeric fields require exact agreement. Empty–empty agreement never inflates a score.

Sorted-neighborhood candidate search is deliberately bounded to20,000 compared pairs; the UI reports incomplete coverage and shows up to100 candidate pairs. Scores are similarities, never identity probabilities. No rows merge automatically.

Review both complete records side by side. Choose a value for every conflicting nonempty field, choose the original row number to retain, acknowledge the merge, and review the actual update/deletion preview. Unambiguous nonempty values are preserved. Keep both records instead records a dismissal only while both complete row fingerprints remain unchanged.

The surviving values keep their original source provenance: confirmed date format, statistical-estimate status and accepted user-entered text follow the selected source. The removed row's original index stays in the audit, and Undo restores both rows.

## Outlier review

Choose a plain numeric measurement, IQR or normalized-MAD sensitivity, and optional grouping. Bounds use at least five original observations per group; previous estimates are excluded. MAD=0, insufficient groups or absent grouping keys are explained. A flagged value is a review suggestion, not inherently incorrect.

Review group bounds and flagged cells. Save the check to highlight it in the sheet. Separately review Keep as valid, Convert to empty, or Cap at the displayed bounds for one or all flagged cells. Keeping a value applies only to the same cell value under the same rule settings. Capping/clearing require explicit confirmation and do not remove rows.

## Shared behavior

Analysis jobs and previews never commit edits. Writes use the existing owner-scoped, revision-checked, background workflow; cancel preserves the last committed copy. Decisions appear in History, complete before/after audit and PDF exports, and support replay-based Undo. Other earlier manual/automatic decisions are retained.

Reviewed-tool decisions are excluded from transferable recipes: fitted models, record merges and row judgements require a fresh review on another dataset. The earlier automatic survey remains unchanged; these tools are optional. Append/join files, general calculated/split columns, business calendars and deep JSON/range expansion were not part of this implementation.

# Percentage scale, ambiguity review, and type cleanup (Phase A)

Bare numbers in a percentage column are genuinely ambiguous. `0.96` can mean
96% (a ratio) or 0.96% (percentage points). DataNeat never guesses: it asks for
one column-level decision and uses that answer consistently.

## Declaring the scale

The column rules now use the existing `percentage_scale` field:

- `""` (not declared): bare values are flagged for review.
- `"points"`: `0.96` means 0.96%.
- `"ratio"`: `0.96` means 96 points when calculating.

The value is stored with the column's rules through the normal rules decision,
so it is recorded in history, undoable, and carried through rename, recipes and
saved files. In the UI it appears in **Column settings → Column data type** when
the type is Percentage, including automatically detected percentage columns.

Declaring a scale does not rewrite cells. Text changes only when the user
applies Normalize Percentage.

## Review issue

When a percentage column has bare values and no declared scale, profiling adds a
`percentage_scale` issue with the bare count and examples. Cell annotations carry
the same kind, so it appears in the header count, the issue drawer, navigation
and the column Insights. Selecting it opens a short explanation and a button
that opens Column settings. The issue is a review flag, not a conversion.

## Gates

- **Missing-value estimates:** mean/median on a percentage column with bare
  values requires a declared scale. With `ratio`, bare values are scaled ×100 for
  calculation; with `points`, they stay as written. Marked values (`10%`) always
  use percentage points. Mixed marked/bare notation still requires normalization
  first. The imputation readiness blocker shows "Bare percentage scale not
  declared".
- **Column rules:** percentage bounds require the declared scale (existing
  `number_for` gate, now with an actionable message).
- **Cross-column arithmetic:** bare percentage columns are rejected with a
  request to declare the scale and normalize to plain numbers; no implicit
  scaling or unit guessing happens in equations.
- **Automatic cleaning:** a percentage column with undeclared bare values is
  skipped with an explicit reason; nothing is converted silently.
- **Outliers:** percentage columns remain excluded from numeric outlier review.

## Retirement of the Salary type

`Salary / numeric amount` was redundant next to Number and Currency and was
removed from the data-type picker and from AI type suggestions. Backend
`salary` remains accepted only for backward compatibility with older saved
rules, recipes and API clients; it is treated as an ordinary numeric measure.
The UI displays a legacy `salary` column as **Number** and saves future type
changes as `numeric`. No existing saved data is rewritten.

## Verification

- `backend/tests/test_percentage_scale.py`: flags and annotations, declaration
  clears them, imputation gate, ratio and points calculations, automatic
  cleaning skip, rule-bounds message.
- Updated `test_percentage_imputation.py` for the explicit-scale requirement.
- Full suite: 729 passed with the final cross-column guard.
- Headless browser: a Rate column with 0.96/0.84/0.60 shows 3 flags → opens the
  panel → Column settings → choose Ratio → Save → 0 flags; the type picker no
  longer offers Salary.
- Analysis schema advances to 10 so existing files refresh their findings
  without changing data, history or revision.

# Issue-specific correction menus

The cell correction panel must never offer an action that cannot address the
cell’s actual issue. `interactive-sheet.tsx` now builds the “Fix option” list
from the cell’s issue kinds and the column’s detected type:

- phone → Standardize phone format (+ manual correction)
- currency → Standardize currency notation (+ manual correction)
- percentage → Include/remove % (+ manual correction)
- symbol/units → Standardize unit notation (+ manual correction)
- time/duration/boolean/capitalization → the matching normalizer
- date issues → date interpretation/format normalization
- whitespace → trim
- negative-value rule → remove minus
- missing → imputation methods (when readiness allows)
- duplicate rows → remove duplicates
- data formats (URL, IP, coordinates, lists/JSON, units, numeric timestamps,
  timezones, localized numbers/fractions) → the matching format action only
- email/type mismatch/odd values → manual corrected value or clear cell only

Generic “Clear affected cells” and “Replace with one value” remain available
because they are valid for any issue.

The suggested correction and the quick-correction selector use the same
mapping, so phone/currency/symbol/percentage suggestions display and apply their
specific normalizer instead of a generic custom placeholder.

Verified in Chromium for phone, currency, URL, boolean, whitespace and email
columns (email/type-mismatch correctly offer only a manual correction).

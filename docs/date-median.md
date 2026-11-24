# Date median imputation

Median and Group median are offered for date/datetime columns, including cached saved profiles. Observed values are parsed explicitly; invalid or ambiguous input is blocked with the original column and spreadsheet row. Previously approved numeric date formats are respected through workflow provenance.

The median is the chronological midpoint of the two central observations (or the central observation for odd counts), calculated with integer microseconds. Date-only output uses the calendar day containing the midpoint. Datetimes preserve time and a consistent source timezone; mixed aware/naive values require normalization. Supported numeric date formats are preserved where possible; month-name/mixed layouts use a supported numeric format. Only missing cells are filled; imputation metadata and format provenance support flags, later formatting, audit and undo.

Validation: full backend suite 246 passing before the cached-profile addition, then all 10 focused date-median tests passing; UI selected Median for Birth_Date and filled 2024-01-03 between 2024-01-01 and 2024-01-05.

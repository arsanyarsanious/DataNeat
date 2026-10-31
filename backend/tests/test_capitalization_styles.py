import pandas as pd
from app.core.issue_detector import detect_case_inconsistency
from app.core.interactive import annotate
from app.core.profiler import profile_dataframe


def test_different_city_names_with_mixed_styles_are_flagged():
    df = pd.DataFrame({"City": ["Alexandria", "CAIRO", "TANTA", "Mansoura"]})
    report = profile_dataframe(df)
    assert detect_case_inconsistency(df.City)["count"] == 4
    preview = annotate(df, report, df)
    assert all(any(issue["kind"] == "capitalization" for issue in row[0]) for row in preview)


def test_acronyms_do_not_create_false_style_conflicts():
    assert detect_case_inconsistency(pd.Series(["IT", "HR", "Operations", "Marketing"], name="Department"))["count"] == 0


def test_consistent_styles_and_numeric_strings_are_not_flagged():
    assert detect_case_inconsistency(pd.Series(["Cairo", "Tanta", "123"], name="City"))["count"] == 0

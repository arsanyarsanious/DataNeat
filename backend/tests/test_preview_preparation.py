import pandas as pd
from app.core.interactive import prepare_original_preview, annotate
from app.core.issue_detector import detect_date_format_inconsistency
from app.core.profiler import profile_dataframe


def test_missing_synonyms_become_empty_without_other_cleanup():
    values = ["N/A", " NULL ", "empty", "Blank", "nil", "Not Available", "not applicable", "#N/A", "", None, " mary  david ", "CAIRO", 0, False, "unknown"]
    original = pd.DataFrame({"Value": values})
    prepared, _ = prepare_original_preview(original)
    assert prepared.Value.tolist()[:10] == [None] * 10
    assert prepared.Value.tolist()[10:] == ["mary david", "CAIRO", 0, False, "unknown"]
    assert original.Value.tolist() == values


def test_mixed_date_formats_are_reported_and_annotated():
    df = pd.DataFrame({"Join_Date": ["13-09-2021", "Aug 30 1995", "July 08, 2018", "09/24/2015", "15/07/1991"]})
    report = profile_dataframe(df)
    assert any(issue["issue"] == "date_format_inconsistency" for issue in report["columns"][0]["issues"])
    assert all(any(issue["kind"] == "date_format" for issue in row[0]) for row in annotate(df, report, df))


def test_ambiguity_alone_does_not_imply_mixed_formats():
    series = pd.Series(["15/07/1991", "05/10/2025"], name="Join_Date")
    assert detect_date_format_inconsistency(series)["count"] == 0

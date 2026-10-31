import pandas as pd
import pytest

from app.core.issue_detector import detect_column_issues
from app.core.cleaner import normalize_boolean


@pytest.mark.parametrize("values", [
    ["Yes", "TRUE", "1", "No", "Y"],
    ["Yes", "TRUE"],
    ["Yes", "False"],
    ["TRUE", "True", "FALSE"],
])
def test_mixed_boolean_labels_are_reported(values):
    issues = detect_column_issues(pd.Series(values, name="Active"), "boolean")
    assert any(issue["issue"] == "boolean_inconsistency" for issue in issues)


@pytest.mark.parametrize("values", [
    ["Yes", "No", "Yes", None], ["TRUE", "FALSE"], ["1", "0"],
    [True, False, True], ["Y", "N"], ["Yes", "Yes"],
])
def test_consistent_boolean_labels_are_not_reported(values):
    issues = detect_column_issues(pd.Series(values, name="Active"), "boolean")
    assert not any(issue["issue"] == "boolean_inconsistency" for issue in issues)


def test_normalization_resolves_redundancy_preserving_missing_and_invalid_values():
    normalized = normalize_boolean(pd.Series(["Yes", "TRUE", "1", "No", "Y", None, "maybe"]))
    assert normalized.tolist() == [True, True, True, False, True, None, "maybe"]
    issues = detect_column_issues(normalized.rename("Active"), "boolean")
    assert not any(issue["issue"] == "boolean_inconsistency" for issue in issues)
    assert any(issue["issue"] == "type_mismatch" for issue in issues)

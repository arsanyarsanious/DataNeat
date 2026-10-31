import pandas as pd
import pytest
from app.core.issue_detector import detect_odd_values, detect_column_issues
from app.core.interactive import annotate
from app.core.profiler import profile_dataframe


@pytest.mark.parametrize("values,expected", [
    ([10, 20, 30, "oops"], "oops"),
    (["Cairo", "Tanta", "Alexandria", 99], 99),
    (["$10", "$20", "$30", "40%"], "40%"),
    ([10, 20, 30, "40%"], "40%"),
])
def test_odd_type_is_identified_with_row(values, expected):
    result = detect_odd_values(pd.Series(values, name="Value"))
    assert result["count"] == 1
    assert result["row_indices"] == [3]
    assert result["examples"] == [str(expected)]


def test_no_guess_without_clear_majority_and_missing_is_excluded():
    assert detect_odd_values(pd.Series([10, 20, "a", "b"]))["count"] == 0
    assert detect_odd_values(pd.Series([10, 20, 30, None, "N/A"]))["count"] == 0
    assert not any(issue["issue"] == "odd_value" for issue in detect_column_issues(pd.Series(["A1", "B2", "C3", 99], name="ID"), "identifier"))


def test_currency_percentage_odd_cell_is_highlighted():
    df = pd.DataFrame({"Salary": ["$10", "$20", "$30", "40%"]})
    rows = annotate(df, profile_dataframe(df), df)
    assert any(issue["kind"] == "odd_value" for issue in rows[3][0])
    assert all(not any(issue["kind"] == "odd_value" for issue in row[0]) for row in rows[:3])

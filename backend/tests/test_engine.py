import pandas as pd
import pytest
from app.core.cleaner import (
    apply_cleaning_plan,
    normalize_boolean,
    normalize_capitalization,
    normalize_dates,
    normalize_missing_values,
    normalize_numeric,
    trim_whitespace,
)
from app.core.cleaning_plan import generate_cleaning_plan
from app.core.date_analyzer import (
    analyze_date_column,
    detect_date_pattern,
    infer_numeric_date_format,
    is_ambiguous_numeric_date,
    is_valid_date,
)
from app.core.file_parser import parse_file
from app.core.issue_detector import (
    detect_case_inconsistency,
    detect_duplicates,
    detect_missing_values,
)
from app.core.profiler import profile_column
from app.core.type_detector import (
    detect_column_type,
    is_boolean,
    is_date,
    is_decimal,
    is_integer,
)
from app.core.validator import validate_cleaning


@pytest.mark.parametrize(
    "name,values,kind",
    [
        ("Salary", ["5,000", "6200", "7100", "8,200"], "integer"),
        ("Active", ["Yes", "TRUE", "1", "No", "Y"], "boolean"),
        ("count", ["0", "1", "0", "1"], "integer"),
        ("Customer_ID", ["001", "002"], "identifier"),
        ("zip", ["12345", "12346"], "identifier"),
        ("date", ["2025-10-05", "Oct 5 2025"], "date"),
        ("amount", ["$5", "$6"], "currency"),
        ("discount", ["10%", "20%"], "percentage"),
        ("time", ["2025-10-05T12:30:00"], "datetime"),
        ("empty", [None, "NA"], "unknown"),
    ],
)
def test_types(name, values, kind):
    assert detect_column_type(pd.Series(values, name=name))["type"] == kind


def test_profile_does_not_modify():
    s = pd.Series([" Cairo ", "NA", None, "cairo", "CAIRO"], name="City")
    original = s.copy(deep=True)
    report = profile_column(s)
    pd.testing.assert_series_equal(s, original)
    assert report["missing_count"] == 2
    assert report["missing_percentage"] == 40
    issue = detect_case_inconsistency(s)
    assert issue["count"] == 3 and issue["conflicting_categories"] == 1
    assert detect_missing_values(pd.Series(["-", "x"]))["count"] == 1


def test_date_evidence_and_preservation():
    s = pd.Series(
        [
            "15/05/2025",
            "05/15/2025",
            "05/10/2025",
            "31/02/2025",
            "2025-99-88",
            "Oct 5 2025",
        ],
        name="Birth_Date",
    )
    report = analyze_date_column(s)
    assert (
        report["conflicting_evidence"]
        and report["ambiguous_count"] == 1
        and report["invalid_count"] == 2
    )
    assert report["dd_mm_evidence"] == 1 and report["mm_dd_evidence"] == 1
    assert is_ambiguous_numeric_date("05/10/2025")
    assert not is_valid_date("31/02/2025")
    assert not is_date("5000")
    assert infer_numeric_date_format("15/05/2025") == "DD/MM/YYYY"
    assert detect_date_pattern("2025/10/05") == "YYYY/MM/DD"
    cleaned = normalize_dates(s, {"interpretation": "preserve"})
    assert cleaned[2] == "05/10/2025" and cleaned[3] == "31/02/2025"
    assert normalize_dates(s, {"interpretation": "day_first"})[2] == "2025-10-05"
    assert normalize_dates(s, {"interpretation": "month_first"})[2] == "2025-05-10"


def test_cleaning_copy_approval_and_validation():
    df = pd.DataFrame(
        {
            "ID": ["001", "002", "002"],
            "City": [" Cairo ", "cairo", "cairo"],
            "Salary": ["5,000", "Unknown", "Unknown"],
        }
    )
    original = df.copy(deep=True)
    plan = generate_cleaning_plan(df)
    assert all(not o["enabled"] for o in plan if o["safety"] != "safe")
    cleaned, logs = apply_cleaning_plan(df, plan)
    assert (
        len(cleaned) == 3
        and cleaned["City"][0] == "Cairo"
        and cleaned["ID"][0] == "001"
    )
    pd.testing.assert_frame_equal(df, original)
    for o in plan:
        o["enabled"] = True
    cleaned, logs = apply_cleaning_plan(df, plan)
    assert len(cleaned) == 2 and cleaned["Salary"][1] == "Unknown"
    report = validate_cleaning(df, cleaned, logs)
    assert report["duplicates_removed"] == 1
    assert report["unresolved_issues"] > 0
    pd.testing.assert_frame_equal(df, original)


def test_transformations():
    assert is_boolean("Y") and is_integer("5,000") and is_decimal("2.5")
    assert trim_whitespace(pd.Series([" A  B "]))[0] == "A B"
    assert normalize_capitalization(pd.Series(["CAIRO"]), "title")[0] == "Cairo"
    assert normalize_missing_values(pd.Series(["NA", "x"]), ["na"])[0] is None
    assert normalize_boolean(pd.Series(["Yes", "maybe"])).tolist() == [True, "maybe"]
    assert normalize_numeric(
        pd.Series(["$5.00", "€7.00", "invalid"]), {"kind": "currency"}
    ).tolist() == ["$5", "€7", "invalid"]
    assert normalize_numeric(pd.Series(["10.00%"]), {"kind": "percentage"})[0] == "10%"
    assert normalize_numeric(pd.Series(["1,23"]), {})[0] == "1,23"
    with pytest.raises(ValueError):
        normalize_capitalization(pd.Series(["a"]), "invalid")


def test_parser_duplicate_headers_and_identifiers():
    df, meta = parse_file(b"ID;City;City\n001; Cairo ;CAIRO\n", "test.csv")
    assert list(df.columns) == ["ID", "City", "City_2"]
    assert df["ID"][0] == "001" and df["City"][0] == " Cairo "
    assert meta["delimiter"] == ";" and meta["header_adjustments"]
    for data in (b"", b"a,b\n1,2,3\n", b"a\n"):
        with pytest.raises(ValueError):
            parse_file(data, "test.csv")


def test_rename_and_selected_duplicates():
    df = pd.DataFrame({"ID": ["001", "001"], "City": ["a", "b"]})
    cleaned, logs = apply_cleaning_plan(
        df,
        [
            {
                "enabled": True,
                "operation": "remove_duplicates",
                "parameters": {"subset": ["ID"]},
            },
            {
                "enabled": True,
                "operation": "rename_column",
                "column": "City",
                "parameters": {"name": "Town"},
            },
        ],
    )
    assert len(cleaned) == 1 and "Town" in cleaned
    assert detect_duplicates(df, ["ID"]) == 1


def test_same_day_month_and_large_decimal():
    assert (
        normalize_dates(pd.Series(["05/05/2025"]), {"interpretation": "preserve"})[0]
        == "2025-05-05"
    )
    assert (
        normalize_numeric(pd.Series(["99999999999999999999.123456789"]), {})[0]
        == "99999999999999999999.123456789"
    )


@pytest.mark.parametrize(
    "value",
    [
        "2025-10-05",
        "2025/10/05",
        "15/05/2025",
        "05/15/2025",
        "15-05-2025",
        "05-15-2025",
        "Oct 5 2025",
        "October 5, 2025",
    ],
)
def test_supported_date_patterns(value):
    assert is_valid_date(value)


def test_mixed_numeric_units_are_preserved():
    values = pd.Series(["100", "10.00%", "$20.00", "€30.00"])
    assert normalize_numeric(values, {"kind": "integer"}).tolist() == [
        "100",
        "10%",
        "$20",
        "€30",
    ]

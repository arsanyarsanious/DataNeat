import pandas as pd
import pytest
from app.core.cleaner import apply_cleaning_plan
from app.core.imputation import impute_missing_values
from app.core.profiler import profile_dataframe
from app.core.validator import validate_cleaning


def run(values, method, **parameters):
    df = pd.DataFrame({"Amount": values})
    original = df.copy(deep=True)
    result, audit = impute_missing_values(df, "Amount", method, parameters)
    pd.testing.assert_frame_equal(df, original)
    for index, value in enumerate(values):
        if value is not None and value != "NA":
            assert result.loc[index, "Amount"] == value
    return result["Amount"].tolist(), audit


@pytest.mark.parametrize(
    "method,values,expected",
    [
        ("mean", [10, None, 20], [10, 15, 20]),
        ("median", [1, None, 2, 100], [1, 2, 2, 100]),
        ("mode", ["red", None, "blue", "red"], ["red", "red", "blue", "red"]),
        ("mode", ["001", None, "002"], ["001", "001", "002"]),
        ("preserve", ["a", None], ["a", None]),
    ],
)
def test_basic_methods(method, values, expected):
    result, audit = run(values, method)
    assert result == expected
    assert audit["imputed_count"] == (0 if method == "preserve" else 1)
    assert audit["missing_after"] == (1 if method == "preserve" else 0)


@pytest.mark.parametrize(
    "values,value,expected",
    [
        (["red", None], "Unknown category", ["red", "Unknown category"]),
        ([10, None], "0", [10, 0]),
        ([None, None], "Unavailable", ["Unavailable", "Unavailable"]),
        (["yes", None, "no"], "false", ["yes", False, "no"]),
        (
            ["2025-01-01", None, "2025-02-01"],
            "2025-03-01",
            ["2025-01-01", "2025-03-01", "2025-02-01"],
        ),
    ],
)
def test_constant_types(values, value, expected):
    result, _ = run(values, "constant", value=value)
    assert result == expected


@pytest.mark.parametrize(
    "method,expected",
    [
        ("group_mean", [10, 15, 20, 100, 100, None, None]),
        ("group_median", [10, 15, 20, 100, 100, None, None]),
        ("group_mode", [10, 10, 20, 100, 100, None, None]),
    ],
)
def test_group_statistics_missing_keys_empty_groups(method, expected):
    df = pd.DataFrame(
        {
            "Entity": ["A", "A", "A", "B", "B", "C", None],
            "Amount": [10, None, 20, 100, None, None, None],
        },
        dtype=object,
    )
    original = df.copy(deep=True)
    cleaned, log = impute_missing_values(df, "Amount", method, {"group_by": ["Entity"]})
    assert cleaned["Amount"].tolist() == expected
    assert log["imputed_count"] == 2 and log["missing_after"] == 2
    assert any("missing group keys" in w for w in log["warnings"])
    pd.testing.assert_frame_equal(original, df)


@pytest.mark.parametrize(
    "method,expected",
    [
        ("forward_fill", [None, 0, 0, 20, None]),
        ("backward_fill", [None, 0, 20, 20, None]),
        ("linear_interpolation", [None, 0, 10, 20, None]),
    ],
)
def test_ordered_methods_preserve_boundaries_and_original_order(method, expected):
    df = pd.DataFrame(
        {"Amount": [None, 0, None, 20, None], "Time": [0, 1, 2, 3, 4]}, dtype=object
    )
    shuffled = df.iloc[[3, 0, 2, 4, 1]].copy()
    original = shuffled.copy(deep=True)
    result, log = impute_missing_values(
        shuffled, "Amount", method, {"order_by": "Time", "single_entity": True}
    )
    assert result["Amount"].tolist() == [expected[i] for i in [3, 0, 2, 4, 1]]
    assert log["missing_after"] == 2 and log["imputed_count"] == 1
    assert log["imputed_cells"] == [
        {"row_index": 2, "spreadsheet_row": 4, "is_imputed": True}
    ]
    pd.testing.assert_frame_equal(original, shuffled)


@pytest.mark.parametrize(
    "method,expected",
    [
        ("group_forward_fill", [1, 1, 3, None, 100, None]),
        ("group_backward_fill", [1, 3, 3, None, 100, None]),
    ],
)
def test_group_directional_methods_never_cross_entities(method, expected):
    df = pd.DataFrame(
        {
            "Amount": [1, None, 3, None, 100, None],
            "Entity": ["A"] * 3 + ["B"] * 3,
            "Time": [1, 2, 3, 1, 2, 3],
        },
        dtype=object,
    )
    result, _ = impute_missing_values(
        df, "Amount", method, {"group_by": ["Entity"], "order_by": "Time"}
    )
    assert result["Amount"].tolist() == expected


def test_time_interpolation_uses_actual_spacing_and_groups():
    df = pd.DataFrame(
        {
            "Amount": [0, None, 30, 100, None, 120],
            "Entity": ["A"] * 3 + ["B"] * 3,
            "Time": ["2025-01-01", "2025-01-02", "2025-01-04"] * 2,
        },
        dtype=object,
    )
    result, log = impute_missing_values(
        df,
        "Amount",
        "linear_interpolation",
        {"group_by": ["Entity"], "order_by": "Time"},
    )
    assert result.loc[1, "Amount"] == 10
    assert result.loc[4, "Amount"] == pytest.approx(100 + 20 / 3)
    assert log["imputed_count"] == 2


@pytest.mark.parametrize(
    "method",
    [
        "mean",
        "median",
        "mode",
        "forward_fill",
        "backward_fill",
        "linear_interpolation",
        "group_mean",
        "group_median",
        "group_mode",
        "group_forward_fill",
        "group_backward_fill",
    ],
)
def test_all_missing_and_empty_columns(method):
    for df in [
        pd.DataFrame({"Amount": [None, None], "Time": [1, 2], "Entity": ["A", "A"]}),
        pd.DataFrame(columns=["Amount", "Time", "Entity"]),
    ]:
        result, log = impute_missing_values(
            df, "Amount", method, {"group_by": ["Entity"], "order_by": "Time"}
        )
        assert result["Amount"].isna().all()
        assert log["imputed_count"] == 0


@pytest.mark.parametrize(
    "method,parameters",
    [
        ("knn", {}),
        ("regression", {}),
        ("constant", {}),
        ("constant", {"value": "NA"}),
        ("constant", {"value": float("inf")}),
        ("group_mean", {}),
        ("mean", {"group_by": "Entity"}),
        ("forward_fill", {}),
        ("forward_fill", {"order_by": "Time"}),
        ("mean", {"group_by": ["Amount"]}),
        ("mean", {"group_by": ["Missing"]}),
        ("forward_fill", {"order_by": "Amount", "single_entity": True}),
    ],
)
def test_invalid_parameters(method, parameters):
    df = pd.DataFrame({"Amount": [10, None, 20], "Time": [1, 2, 3]}, dtype=object)
    with pytest.raises(ValueError):
        impute_missing_values(df, "Amount", method, parameters)


@pytest.mark.parametrize(
    "values",
    [
        ["10", "invalid", None],
        ["$10", None, "$20"],
        ["10%", None, "20%"],
        ["001", None, "002"],
        [True, None, False],
        [float("inf"), None, 20],
    ],
)
def test_unsafe_numeric_target_is_blocked(values):
    with pytest.raises(ValueError):
        run(values, "mean")


@pytest.mark.parametrize(
    "times",
    [
        [1, None, 3],
        [1, 1, 3],
        ["05/10/2025", "06/10/2025", "07/10/2025"],
        ["2025-99-88", "2025-01-02", "2025-01-03"],
    ],
)
def test_invalid_ordering_dependency_is_blocked(times):
    with pytest.raises(ValueError):
        impute_missing_values(
            pd.DataFrame({"Amount": [0, None, 20], "Time": times}, dtype=object),
            "Amount",
            "linear_interpolation",
            {"order_by": "Time", "single_entity": True},
        )


def test_reproducible_mode_ties_and_preserved_missing_markers():
    df = pd.DataFrame({"Amount": ["red", "NA", "blue", "-", "red", "blue"]})
    first, log = impute_missing_values(df, "Amount", "mode", {})
    second, repeat = impute_missing_values(df, "Amount", "mode", {})
    pd.testing.assert_frame_equal(first, second)
    assert log == repeat and first.loc[1, "Amount"] == "red"


def test_recommendations_statistics_missing_patterns():
    df = pd.DataFrame(
        {"Amount": [1, 2, 2, 2, 100, None], "Category": ["x", "x", "y", "y", "x", None]}
    )
    report = profile_dataframe(df)
    amount, category = report["columns"]
    assert amount["imputation"]["method"] == "median"
    assert amount["imputation"]["statistics"]["numeric"]["outlier_count"] == 2
    assert category["imputation"]["method"] == "mode"
    assert report["missing_patterns"] == [
        {"columns": ["Amount", "Category"], "rows": 1}
    ]
    assert "random" in amount["imputation"]["warnings"][0]


def test_pipeline_orders_dependencies_requires_approval_and_audits():
    df = pd.DataFrame(
        {
            "Amount": ["10", "unknown", "20"],
            "Time": ["2025-01-01", "02/01/2025", "2025-01-03"],
        }
    )
    operations = [
        {
            "id": "impute",
            "column": "Amount",
            "operation": "impute_missing_values",
            "enabled": True,
            "parameters": {
                "method": "linear_interpolation",
                "order_by": "Time",
                "single_entity": True,
                "confirmed": True,
            },
        },
        {
            "column": "Time",
            "operation": "normalize_dates",
            "enabled": True,
            "parameters": {"interpretation": "day_first"},
        },
        {
            "column": "Amount",
            "operation": "normalize_missing_values",
            "enabled": True,
            "parameters": {"markers": ["unknown"]},
        },
        {
            "column": "Amount",
            "operation": "rename_column",
            "enabled": True,
            "parameters": {"name": "Value"},
        },
    ]
    original = df.copy(deep=True)
    cleaned, logs = apply_cleaning_plan(df, operations)
    assert cleaned.loc[1, "Value"] == 15
    assert [l["operation"] for l in logs] == [
        "normalize_missing_values",
        "normalize_dates",
        "impute_missing_values",
        "rename_column",
    ]
    validation = validate_cleaning(df, cleaned, logs)
    assert validation["imputed_cells"] == 1
    assert validation["imputation"][0]["missing_before"] == 1
    pd.testing.assert_frame_equal(original, df)
    operations[0]["parameters"]["confirmed"] = False
    with pytest.raises(ValueError, match="Confirm imputation"):
        apply_cleaning_plan(df, operations)
    apply_cleaning_plan(df, operations, require_approval=False)
    operations[1]["enabled"] = False
    with pytest.raises(ValueError, match="Ordering needs"):
        apply_cleaning_plan(df, operations, require_approval=False)


def test_contextual_group_and_sequence_suggestions_are_conditional():
    df = pd.DataFrame(
        {
            "Entity": ["A", "A", "B", "B"],
            "Time": [1, 2, 1, 2],
            "Reading": [10, None, 100, None],
        }
    )
    report = profile_dataframe(df)
    reading = report["columns"][2]["imputation"]
    suggestions = reading["contextual_recommendations"]
    assert any(
        s["method"] == "group_median" and s["group_by"] == ["Entity"]
        for s in suggestions
    )
    assert any(
        s["method"] == "linear_interpolation" and s["order_by"] == "Time"
        for s in suggestions
    )
    assert all(
        "If" in s["explanation"] or "if" in s["explanation"] for s in suggestions
    )


def test_dirty_numeric_column_can_resolve_custom_marker_dependency():
    df = pd.DataFrame({"Amount": ["10", None, "unknown", "20"]}, dtype=object)
    suggestion = profile_dataframe(df)["columns"][0]["imputation"]
    assert "mean" in suggestion["available_methods"]
    assert suggestion["method"] == "constant"
    operations = [
        {
            "column": "Amount",
            "operation": "impute_missing_values",
            "enabled": True,
            "parameters": {"method": "mean", "confirmed": True},
        },
        {
            "column": "Amount",
            "operation": "normalize_missing_values",
            "enabled": True,
            "parameters": {"markers": ["unknown"]},
        },
    ]
    cleaned, logs = apply_cleaning_plan(df, operations)
    assert cleaned["Amount"].tolist() == ["10", 15, 15, "20"]
    assert logs[-1]["imputed_count"] == 2


def test_existing_rename_then_transform_order_is_preserved_without_imputation():
    df = pd.DataFrame({"Name": [" value "]})
    operations = [
        {
            "column": "Name",
            "operation": "rename_column",
            "enabled": True,
            "parameters": {"name": "Label"},
        },
        {
            "column": "Label",
            "operation": "trim_whitespace",
            "enabled": True,
            "parameters": {},
        },
    ]
    result, _ = apply_cleaning_plan(df, operations)
    assert result.loc[0, "Label"] == "value"


def test_salary_currency_exposes_numeric_methods_and_requires_conversion():
    df = pd.DataFrame({"Salary": ["$1,000", None, "$3,000"]}, dtype=object)
    report = profile_dataframe(df)["columns"][0]
    assert report["detected_type"] == "currency"
    assert {"mean", "median", "group_mean", "group_median"}.issubset(
        report["imputation"]["available_methods"]
    )
    with pytest.raises(ValueError):
        impute_missing_values(df, "Salary", "mean", {})
    operations = [
        {
            "column": "Salary",
            "operation": "impute_missing_values",
            "enabled": True,
            "parameters": {"method": "mean", "confirmed": True},
        },
        {
            "column": "Salary",
            "operation": "normalize_currency",
            "enabled": True,
            "parameters": {"action": "remove"},
        },
    ]
    cleaned, logs = apply_cleaning_plan(df, operations)
    assert cleaned["Salary"].tolist() == ["1000", 2000, "3000"]
    assert logs[-1]["imputed_count"] == 1


def test_categorical_salary_still_offers_arithmetic_with_dependency_warning():
    df = pd.DataFrame({"Salary": ["1000", "Unknown", "Unknown", None]}, dtype=object)
    report = profile_dataframe(df)["columns"][0]
    assert "mean" in report["imputation"]["available_methods"]
    assert "median" in report["imputation"]["available_methods"]
    with pytest.raises(ValueError):
        impute_missing_values(df, "Salary", "median", {})
    protected = pd.DataFrame({"Salary_ID": ["001", None, "002"]})
    assert (
        "mean"
        not in profile_dataframe(protected)["columns"][0]["imputation"][
            "available_methods"
        ]
    )

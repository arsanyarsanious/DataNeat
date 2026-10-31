import pandas as pd
import pytest
from app.core.imputation import impute_missing_values
from app.core.profiler import profile_dataframe


@pytest.mark.parametrize("method", ["mean", "median", "group_mean", "group_median"])
def test_percentage_imputation_is_numeric_and_preserves_notation(method):
    df = pd.DataFrame({"Performance_Score": ["10%", None, "30 %"], "Department": ["IT"] * 3})
    profile = profile_dataframe(df)["columns"][0]
    assert profile["detected_type"] == "percentage"
    assert method in profile["imputation"]["available_methods"]
    result, audit = impute_missing_values(df, "Performance_Score", method, {"group_by": ["Department"]} if method.startswith("group_") else {})
    assert result.Performance_Score.tolist() == ["10%", "20%", "30 %"]
    assert audit["imputed_count"] == 1
    assert df.Performance_Score.tolist() == ["10%", None, "30 %"]


def test_percentage_mixed_scales_require_explicit_normalization():
    df = pd.DataFrame({"Rate": ["10%", None, "0.3"]})
    with pytest.raises(ValueError, match="percentage points or fractions"):
        impute_missing_values(df, "Rate", "mean", {})


def test_bare_ratio_scale_is_preserved():
    df = pd.DataFrame({"Rate": ["0.1", None, "0.3"]})
    result, _ = impute_missing_values(df, "Rate", "mean", {})
    assert result.Rate.tolist() == ["0.1", .2, "0.3"]

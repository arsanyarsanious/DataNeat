"""Dispatch reviewed tools through the same versioned working-copy workflow."""
from importlib import import_module

TOOLS = {"cross_column", "model_imputation", "record_matching", "outliers"}


def module(tool):
    if tool not in TOOLS:
        raise ValueError("Choose a supported cleaning tool")
    return import_module(".outlier_review" if tool == "outliers" else "." + tool, __package__)


def validate_settings(settings):
    tool = settings.get("tool")
    return {"tool": tool, **module(tool).validate_settings({k: v for k, v in settings.items() if k != "tool"})}


def public_detail(value):
    if isinstance(value, dict):
        return {key: public_detail(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [public_detail(item) for item in value]
    return value


def review(record, settings, check=lambda: None):
    config = validate_settings(settings)
    if config["tool"] == "model_imputation":
        from .imputation_readiness import ensure_imputation_ready
        ensure_imputation_ready(record, config["target"], check, acknowledged=config.get("inconsistencies_acknowledged") is True)
    return public_detail(module(config.pop("tool")).review(record, config, check))


def apply(record, settings, check=lambda: None, *, enforce_imputation_readiness=True):
    config = validate_settings(settings)
    if config["tool"] == "model_imputation" and enforce_imputation_readiness:
        from .imputation_readiness import ensure_imputation_ready
        ensure_imputation_ready(record, config["target"], check, acknowledged=config.get("inconsistencies_acknowledged") is True)
    after, detail = module(config.pop("tool")).apply(record, config, check)
    return after, public_detail(detail)

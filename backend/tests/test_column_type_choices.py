import pytest
from test_workflows import client, upload, job, wait


def choose(client, fid, revision, column, kind, **extra):
    result = wait(client, job(client, fid, revision, "decision", decision={
        "kind": "rules", "column": column, "settings": {"type": kind, **extra}}))
    assert result["status"] == "completed", result
    return client.get(f"/api/files/{fid}/editor").json()


def test_phone_override_reset_and_undo_preserve_values(client):
    fid, initial = upload(client, b"Phone\n00123456789\n00234567890\nnot-a-phone\n")
    assert initial["profile"]["columns"][0]["detected_type"] == "phone"
    text = choose(client, fid, 0, "Phone", "text", unique=True)
    assert text["preview"]["rows"] == initial["preview"]["rows"]
    assert text["profile"]["columns"][0]["detected_type"] == "text"
    assert not any(i["kind"] == "phone" for row in text["preview"]["cell_issues"] for i in row[0])
    serial = choose(client, fid, 1, "Phone", "identifier", unique=True)
    assert serial["profile"]["columns"][0]["intent"]["unique"]
    assert serial["preview"]["rows"][0][0] == "00123456789"
    auto = choose(client, fid, 2, "Phone", "", unique=True)
    assert auto["profile"]["columns"][0]["detected_type"] == "phone"
    undone = wait(client, job(client, fid, 3, "undo", step_id=auto["changes"][-1]["id"]))
    assert undone["status"] == "completed", undone
    restored = client.get(f"/api/files/{fid}/editor").json()
    assert restored["profile"]["columns"][0]["detected_type"] == "identifier"
    assert restored["preview"]["rows"] == initial["preview"]["rows"]


def test_email_name_no_longer_overrides_text(client):
    fid, _ = upload(client, b"Email\nno address supplied\nnot applicable here\n")
    sheet = choose(client, fid, 0, "Email", "text")
    assert not any(i["kind"] == "email" for row in sheet["preview"]["cell_issues"] for i in row[0])


def test_declared_text_salary_has_no_numeric_imputation(client):
    fid, _ = upload(client, b"Salary,Row\n100,a\n200,b\n,c\n")
    sheet = choose(client, fid, 0, "Salary", "text")
    methods = sheet["profile"]["columns"][0]["imputation"]["available_methods"]
    assert not {"mean", "median", "group_mean", "group_median", "linear_interpolation"} & set(methods)


@pytest.mark.parametrize("kind,expected,value", [
    ("numeric", "decimal", "123"), ("salary", "decimal", "123.50"),
    ("location", "category", "Cairo"), ("category", "category", "Retail"),
    ("date", "date", "2024-12-13"), ("datetime", "datetime", "2024-12-13 14:00:00"),
    ("time", "time", "2:30 PM"), ("duration", "duration", "1 hour 30 min"),
    ("boolean", "boolean", "yes"), ("email", "email", "test@example.test"),
    ("phone", "phone", "+201234567890"), ("identifier", "identifier", "00123"),
    ("currency", "currency", "$123"), ("percentage", "percentage", "12%"),
    ("coordinate", "coordinate", "30.04"), ("url", "url", "https://example.test"),
    ("ip", "ip", "192.0.2.1"),
])
def test_explicit_types_override_misleading_name(client, kind, expected, value):
    fid, original = upload(client, f"Phone\n{value}\n".encode())
    sheet = choose(client, fid, 0, "Phone", kind)
    assert sheet["profile"]["columns"][0]["detected_type"] == expected
    assert sheet["preview"]["rows"] == original["preview"]["rows"]
    assert not any(i["kind"] == "rule_type" for row in sheet["preview"]["cell_issues"] for i in row[0])


def test_clock_choice_flags_invalid_and_offers_time_fix(client):
    fid, _ = upload(client, b"Event\n2:30 PM\n14:30:00\n25:99\n")
    sheet = choose(client, fid, 0, "Event", "time")
    assert "time" in {i["kind"] for i in sheet["preview"]["cell_issues"][0][0]}
    assert "invalid_time" in {i["kind"] for i in sheet["preview"]["cell_issues"][2][0]}


def test_type_choice_survives_rename(client):
    fid, _ = upload(client, b"Phone\n00123\n00234\n")
    choose(client, fid, 0, "Phone", "identifier")
    result = wait(client, job(client, fid, 1, "decision", decision={"kind": "rename", "column": "Phone", "settings": {"name": "Reference"}}))
    assert result["status"] == "completed", result
    sheet = client.get(f"/api/files/{fid}/editor").json()
    assert sheet["profile"]["columns"][0]["intent"]["type"] == "identifier"


@pytest.mark.parametrize("value", ["30.04 N", "31.23 E", "30.04, 31.23"])
def test_coordinate_choice_accepts_axis_or_pair_without_changing_value(client, value):
    from app.core.workflow import matches_intent
    assert matches_intent(value, {"type": "coordinate"})
    assert not matches_intent("999 N", {"type": "coordinate"})

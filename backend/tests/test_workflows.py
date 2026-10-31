import io
import csv
import json
import time
import threading
import zipfile

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from app.main import app, store, rate
from app.core.workflow import prepare, profile_record, apply_decision, ensure_workflow, replay_without, suggested_groups, Recipe, ColumnRule
from test_xlsx_formula_results import with_cached_results


@pytest.fixture
def client(tmp_path):
    store.root = tmp_path
    store.jobs.clear(); rate.clear()
    return TestClient(app)


def upload(client, csv=b"ID,City,Salary\n001, Cairo ,$10\n002,Kairo,$30\n003,NA,unknown\n004,Cairo,\n"):
    result = client.post("/api/files/upload", files={"file": ("workflow.csv", csv, "text/csv")})
    assert result.status_code == 200, result.text
    fid = result.json()["file_id"]
    result = client.post(f"/api/files/{fid}/workflow/init")
    assert result.status_code == 200, result.text
    return fid, result.json()


@pytest.mark.parametrize('action,parameters,source,expected',[
 ('normalize_number_format',{'locale':'comma_decimal'},'1.234,56','1234.56'),
 ('convert_units',{'target_unit':'m'},'100 cm','1 m'),
 ('convert_numeric_dates',{'source':'unix_milliseconds'},'1000','1970-01-01T00:00:01+00:00'),
 ('convert_timezone',{'target_zone':'UTC'},'2024-01-01T12:00:00 America/New_York','2024-01-01T17:00:00+00:00'),
 ('normalize_structured',{'trim_items':True,'deduplicate':True},'[" Red ","Red"]','["Red"]'),
 ('normalize_coordinates',{'axis':'lon_lat'},'31, 30','30, 31'),
 ('normalize_url',{},'HTTPS://EXAMPLE.COM/Case','https://example.com/Case'),
 ('normalize_ip',{},'2001:0db8:0:0:0:0:0:1','2001:db8::1'),
])
def test_specialized_formats_workflow_apply_and_undo(client,action,parameters,source,expected):
    content=io.StringIO();writer=csv.writer(content);writer.writerow(['Value']);writer.writerow([source])
    fid,initial=upload(client,content.getvalue().encode())
    body={'revision':0,'column':'Value','row_index':0,'scope':'column','action':action,'parameters':parameters}
    preview=client.post(f'/api/files/{fid}/editor/fix',json=body)
    assert preview.status_code==200,preview.text
    assert preview.json()['proposal']['changed_cells']==1
    applied=wait(client,job(client,fid,0,'decision',decision={'kind':'fix','body':body}))
    assert applied['status']=='completed',applied
    current=client.get(f'/api/files/{fid}/editor').json()
    assert current['preview']['rows'][0][0]==expected
    undo=wait(client,job(client,fid,1,'undo',step_id=current['changes'][-1]['id']))
    assert undo['status']=='completed',undo
    assert client.get(f'/api/files/{fid}/editor').json()['preview']['rows'][0][0]==source


def test_expand_json_tracks_new_columns_and_undo(client):
    content=io.StringIO();writer=csv.writer(content);writer.writerow(['Meta']);writer.writerow(['{"code":"001","n":2}'])
    fid,initial=upload(client,content.getvalue().encode())
    body={'revision':0,'column':'Meta','row_index':0,'scope':'column','action':'expand_structured','parameters':{}}
    preview=client.post(f'/api/files/{fid}/editor/fix',json=body)
    assert preview.status_code==200,preview.text
    assert preview.json()['proposal']['changed_cells']==2
    result=wait(client,job(client,fid,0,'decision',decision={'kind':'fix','body':body}))
    assert result['status']=='completed',result
    current=client.get(f'/api/files/{fid}/editor').json()
    assert current['preview']['columns']==['Meta','Meta.code','Meta.n']
    assert current['preview']['rows'][0]==['{"code":"001","n":2}','001',2]
    assert current['changes'][-1]['changed_cells']==2
    record=store.get(fid,client.cookies.get('dataneat_session'))
    assert {c['column'] for c in record['complete_changes']}=={'Meta.code','Meta.n'}
    undo=wait(client,job(client,fid,1,'undo',step_id=current['changes'][-1]['id']))
    assert undo['status']=='completed',undo
    restored=client.get(f'/api/files/{fid}/editor').json()
    assert restored['preview']['columns']==['Meta']
    assert restored['preview']['rows']==initial['preview']['rows']


def test_date_pattern_editor_audit_and_undo(client):
    fid,initial=upload(client,b'Date,Sequence\n2024-01-01,1\n,2\n2024-01-07,3\n2024-01-10,4\n')
    body={'revision':0,'column':'Date','row_index':1,'scope':'column','action':'impute_missing_values','parameters':{'method':'date_sequence','order_by':'Sequence','single_entity':True}}
    preview=client.post(f'/api/files/{fid}/editor/fix',json=body)
    assert preview.status_code==200,preview.text
    assert preview.json()['proposal']['changed_cells']==1
    result=wait(client,job(client,fid,0,'decision',decision={'kind':'fix','body':body}))
    assert result['status']=='completed',result
    current=client.get(f'/api/files/{fid}/editor').json()
    assert current['preview']['rows'][1][0]=='2024-01-04'
    assert current['preview']['is_imputed'][1][0]
    entry=current['changes'][-1]
    assert entry['imputation']['detected_pattern']['observed_points']==3
    assert 'date_sequence' in current['changes'][-1]['parameters']['method']
    undone=wait(client,job(client,fid,1,'undo',step_id=entry['id']))
    assert undone['status']=='completed',undone
    assert client.get(f'/api/files/{fid}/editor').json()['preview']['rows'][1][0]==initial['preview']['rows'][1][0]


def test_negative_policy_flags_repairs_undo_and_preserves_other_rules(client):
    fid,initial=upload(client,b'Temperature_K,Other\n-5,-1\n-2,-2\n0,-3\n15,-4\nunknown,-5\n')
    def current(): return client.get(f'/api/files/{fid}/editor').json()
    def decide(decision):
        result=wait(client,job(client,fid,current()['revision'],'decision',decision=decision))
        assert result['status']=='completed',result
        return current()
    assert not any(flag['kind']=='rule_negative' for row in initial['preview']['cell_issues'] for cell in row for flag in cell)
    decide({'kind':'rules','column':'Temperature_K','settings':{'required':True,'maximum':'500'}})
    denied=decide({'kind':'negative_policy','column':'Temperature_K','settings':{'allow_negative':False}})
    column=denied['profile']['columns'][0]
    assert column['intent']['required'] and column['intent']['maximum']=='500'
    assert next(i['count'] for i in column['issues'] if i['issue']=='rule_negative')==2
    assert denied['preview']['rows'][0][0]=='-5'
    assert any(i['kind']=='rule_negative' and i['classification']=='invalid' for i in denied['preview']['cell_issues'][0][0])
    assert not any(i['kind']=='rule_negative' for i in denied['preview']['cell_issues'][2][0])
    fixed=decide({'kind':'fix','body':{'revision':denied['revision'],'column':'Temperature_K','row_index':0,'scope':'column','action':'absolute_values'}})
    assert [r[0] for r in fixed['preview']['rows']]==['5','2','0','15','unknown']
    assert [r[1] for r in fixed['preview']['rows']]==['-1','-2','-3','-4','-5']
    assert not any(i['issue']=='rule_negative' for i in fixed['profile']['columns'][0]['issues'])
    result=wait(client,job(client,fid,fixed['revision'],'undo',step_id=fixed['changes'][-1]['id']))
    assert result['status']=='completed',result
    restored=current()
    assert restored['preview']['rows'][0][0]=='-5'
    assert next(i['count'] for i in restored['profile']['columns'][0]['issues'] if i['issue']=='rule_negative')==2
    allowed=decide({'kind':'negative_policy','column':'Temperature_K','settings':{'allow_negative':True}})
    assert not any(i['issue']=='rule_negative' for i in allowed['profile']['columns'][0]['issues'])
    assert allowed['preview']['rows'][0][0]=='-5'
    # Clearing by issue clears all different negative magnitudes, not positives.
    denied=decide({'kind':'negative_policy','column':'Temperature_K','settings':{'allow_negative':False}})
    cleared=decide({'kind':'fix','body':{'revision':denied['revision'],'column':'Temperature_K','row_index':0,'scope':'issue','action':'replace','value':None,'parameters':{'issue_kind':'rule_negative'}}})
    assert [r[0] for r in cleared['preview']['rows']]==[None,None,'0','15','unknown']


def job(client, fid, revision, operation, **values):
    response = client.post(f"/api/files/{fid}/workflow/jobs", json={"revision": revision, "operation": operation, **values})
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


def wait(client, key):
    for _ in range(300):
        rate.clear()
        response = client.get(f"/api/workflow-jobs/{key}")
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] not in ("queued", "running"):
            return data
        time.sleep(.01)
    pytest.fail("Job did not complete")


def test_raw_preview_reviewed_preparation_and_undo(client):
    fid, initial = upload(client)
    assert initial["preview"]["rows"][0] == ["001", " Cairo ", "$10"]
    assert initial["preview"]["rows"][2][1] == "NA"
    decision = {"kind": "preparation", "settings": {"columns": {"ID": {"excluded": True}, "City": {"markers": [""]}}}}
    preview = wait(client, job(client, fid, 0, "preview", decision=decision))
    assert preview["status"] == "completed", preview
    assert preview["result"]["proposal"]["changed_cells"] == 2  # outer whitespace plus actual empty Salary
    assert client.get(f"/api/files/{fid}/editor").json()["revision"] == 0
    result = wait(client, job(client, fid, 0, "decision", decision=decision))
    assert result["status"] == "completed", result
    current = client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0][1] == "Cairo"
    assert current["preview"]["rows"][2][1] == "NA"
    assert not any(i["kind"] == "missing" for i in current["preview"]["cell_issues"][2][1])
    audit = client.get(f"/api/files/{fid}/workflow/changes").json()
    assert audit["total"] == 2 and audit["rows"][0]["spreadsheet_row"] == 2
    assert client.post(f"/api/files/{fid}/editor/undo/{current['changes'][-1]['id']}?revision=1").status_code == 409
    undo = wait(client, job(client, fid, 1, "undo", step_id=current["changes"][-1]["id"]))
    assert undo["status"] == "completed", undo
    restored = client.get(f"/api/files/{fid}/editor").json()
    assert restored["preview"]["rows"][0][1] == " Cairo "
    assert restored["revision"] == 2


def test_column_rules_and_ignore_reversal(client):
    fid, _ = upload(client)
    decision = {"kind": "rules", "column": "Salary", "settings": {"type": "currency", "currency": "$", "minimum": "20", "required": True}}
    result = wait(client, job(client, fid, 0, "decision", decision=decision))
    assert result["status"] == "completed", result
    current = client.get(f"/api/files/{fid}/editor").json()
    assert any(i["kind"] == "rule_range" for i in current["preview"]["cell_issues"][0][2])
    assert any(i["kind"] == "rule_required" for i in current["preview"]["cell_issues"][3][2])
    ignored = {"kind": "ignore", "column": "Salary", "issue": "rule_range", "row_index": 0, "value": "$10", "reason": "Verified exception"}
    assert wait(client, job(client, fid, 1, "decision", decision=ignored))["status"] == "completed"
    current = client.get(f"/api/files/{fid}/editor").json()
    assert not any(i["kind"] == "rule_range" for i in current["preview"]["cell_issues"][0][2])
    assert len(client.get(f"/api/files/{fid}/workflow/settings").json()["ignored"]) == 1
    assert wait(client, job(client, fid, 2, "undo", step_id=current["changes"][-1]["id"]))["status"] == "completed"
    current = client.get(f"/api/files/{fid}/editor").json()
    assert any(i["kind"] == "rule_range" for i in current["preview"]["cell_issues"][0][2])


def test_recipe_replay_mapping_and_compatibility(client):
    fid, _ = upload(client)
    body = {"revision": 0, "column": "City", "row_index": 1, "scope": "values", "action": "replace", "value": "Cairo", "parameters": {"source_values": ["Cairo", "Kairo"]}}
    assert wait(client, job(client, fid, 0, "decision", decision={"kind": "fix", "body": body}))["status"] == "completed"
    recipe = client.get(f"/api/files/{fid}/workflow/recipe").json()
    assert recipe["version"] == 1 and len(recipe["steps"]) == 1
    other, _ = upload(client, b"City,New\nKairo,x\nAlexandria,y\n")
    preview = wait(client, job(client, other, 0, "recipe_preview", recipe=recipe))
    assert preview["status"] == "completed", preview
    assert preview["result"]["changed_cells"] == 1
    assert preview["result"]["extra_columns"] == ["New"]
    assert preview["result"]["mapping_warnings"][0]["unmatched_values"] == ["Cairo"]
    assert client.get(f"/api/files/{other}/editor").json()["preview"]["rows"][0][0] == "Kairo"
    assert wait(client, job(client, other, 0, "recipe", recipe=recipe))["status"] == "completed"
    assert client.get(f"/api/files/{other}/editor").json()["preview"]["rows"][0][0] == "Cairo"
    missing, _ = upload(client, b"Other\nx\n")
    assert client.post(f"/api/files/{missing}/workflow/recipe-check", json=recipe).json()["missing_columns"] == ["City"]
    assert wait(client, job(client, missing, 0, "recipe", recipe=recipe))["status"] == "failed"


def test_cancel_and_stale_commit_preserve_data_and_health(client, monkeypatch):
    import app.services.workflow_jobs as jobs_module
    original = jobs_module.apply_decision
    entered, release = threading.Event(), threading.Event()
    def slow(*args, **kwargs):
        entered.set(); release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(jobs_module, "apply_decision", slow)
    fid, _ = upload(client)
    key = job(client, fid, 0, "decision", decision={"kind": "preparation"})
    assert entered.wait(1)
    assert client.get("/api/health").status_code == 200
    outsider = TestClient(app)
    assert outsider.get(f"/api/workflow-jobs/{key}").status_code == 404
    assert outsider.post(f"/api/workflow-jobs/{key}/cancel").status_code == 404
    assert client.post(f"/api/workflow-jobs/{key}/cancel").status_code == 200
    release.set()
    assert wait(client, key)["status"] == "cancelled"
    assert client.get(f"/api/files/{fid}/editor").json()["revision"] == 0
    entered.clear(); release.clear()
    key = job(client, fid, 0, "decision", decision={"kind": "preparation"})
    assert entered.wait(1)
    record = store.get(fid, client.cookies.get("dataneat_session")); record["editor_revision"] = 10; store.save(record)
    release.set()
    assert wait(client, key)["status"] == "failed"
    assert client.get(f"/api/files/{fid}/editor").json()["revision"] == 10


def test_exports_review_package_and_filtered_log(client):
    fid, _ = upload(client)
    assert wait(client, job(client, fid, 0, "decision", decision={"kind": "preparation"}))["status"] == "completed"
    for fmt in ("xlsx", "csv", "report", "changes", "package"):
        key = job(client, fid, 1, "export", format=fmt, include_changes=True)
        status = wait(client, key)
        assert status["status"] == "completed", status
        response = client.get(status["result"]["download"])
        assert response.status_code == 200
        assert TestClient(app).get(status["result"]["download"]).status_code == 404
        if fmt == "report": assert response.content.startswith(b"%PDF")
        if fmt == "changes": assert response.json()["changes"]
        if fmt == "package":
            archive = zipfile.ZipFile(io.BytesIO(response.content))
            assert set(archive.namelist()) == {"report.pdf", "recipe.json", "README.txt", "changes.json"}
        if fmt == "xlsx":
            wb = load_workbook(io.BytesIO(response.content)); assert wb.active["A2"].value == "001"
    review = client.get(f"/api/files/{fid}/workflow/changes?column=City&search=Cairo&revision=1").json()
    assert review["total"] == 1


def test_preparation_unicode_and_no_internal_collapse_by_default():
    df = pd.DataFrame({"Text": ["  اسم  مركب  ", "NA", "0", "false", ""], "Code": ["001", "NA", "01", "02", "03"]})
    cleaned = prepare(df, {"columns": {"Code": {"excluded": True}, "Text": {"markers": [""]}}})
    assert cleaned["Text"].tolist() == ["اسم  مركب", "NA", "0", "false", None]
    assert cleaned["Code"].tolist() == df["Code"].tolist()


def test_legitimate_exceptions_and_rule_boundaries():
    for settings in ({"minimum": "NaN"}, {"minimum": "4", "maximum": "3"}, {"date_min": "2025-99-88"}):
        with pytest.raises(ValueError): ColumnRule(**settings)
    record = {"editor_df": pd.DataFrame({"Code": ["001", "NA", "003"], "Active": ["yes", "yes", "yes"], "Rate": ["10%", "0.2", "bad"]}), "editor_revision": 0, "column_rules": {"Code": {"type": "identifier", "markers": [""]}, "Active": {"type": "boolean"}, "Rate": {"type": "percentage", "percentage_scale": "ratio", "minimum": "0", "maximum": "100"}}}
    profile_record(record)
    code = record["editor_profile"]["columns"][0]
    assert code["missing_count"] == 0 and code["detected_type"] == "identifier"
    assert not record["editor_profile"]["columns"][1]["rule_findings"]
    assert record["editor_profile"]["columns"][2]["rule_findings"]
    with pytest.raises(ValueError, match="protected"):
        apply_decision(record, {"kind": "fix", "body": {"revision": 0, "column": "Code", "row_index": 0, "action": "normalize_numeric", "scope": "column"}})


def test_suggestions_are_local_candidates_not_automatic_changes():
    entries = [{"value": value, "count": 2} for value in ("Cairo", "Kairo", "CAIRO", "Alexandria")]
    groups = suggested_groups(entries)
    assert groups and "Cairo" in groups[0]["values"] and "Kairo" in groups[0]["values"]
    assert "Alexandria" not in groups[0]["values"]


def test_xlsx_roundtrip_boundaries(client):
    wb = Workbook(); ws = wb.active; ws.title = "First"; ws.append(["ID", "Formula", "Date"])
    from datetime import datetime
    ws.append([123, "=1+1", datetime(2020, 1, 2)]); ws["A2"].number_format = "00000"; ws["A2"].font = ws["A2"].font.copy(bold=True)
    wb.create_sheet("Second").append(["Other"])
    source = io.BytesIO(); wb.save(source)
    content = with_cached_results(source.getvalue(), {"B2": ("n", 2)})
    result = client.post("/api/files/upload", files={"file": ("book.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}).json()
    assert result["metadata"]["formula_cells"] == 1 and result["metadata"]["sheets"] == ["First", "Second"]
    assert "does not preserve" in result["metadata"]["compatibility_warning"]
    fid = result["file_id"]; client.post(f"/api/files/{fid}/workflow/init")
    key = job(client, fid, 0, "export", format="xlsx"); status = wait(client, key)
    exported = load_workbook(io.BytesIO(client.get(status["result"]["download"]).content))
    assert len(exported.sheetnames) == 1
    assert exported.active["A2"].value == "00123"
    assert exported.active["B2"].data_type != "f" and exported.active["B2"].value == 2
    assert not exported.active["A2"].font.bold


def test_undo_dependency_conflict_is_atomic(client):
    fid, _ = upload(client)
    assert wait(client, job(client, fid, 0, "decision", decision={"kind": "preparation"}))["status"] == "completed"
    current = client.get(f"/api/files/{fid}/editor").json()
    prep_id = current["changes"][0]["id"]
    body = {"revision": 1, "column": "City", "row_index": 0, "scope": "values", "action": "replace", "value": "CAIRO", "parameters": {"source_values": ["Cairo", "Kairo"]}}
    assert wait(client, job(client, fid, 1, "decision", decision={"kind": "fix", "body": body}))["status"] == "completed"
    # Removing the preparation changes the source spelling set: test a value that exists only after trim.
    record = store.get(fid, client.cookies.get("dataneat_session"))
    record["workflow_base"]["editor_df"].loc[3,"City"] = " Cairo "
    store.save(record)
    result = wait(client, job(client, fid, 2, "undo", step_id=prep_id))
    assert result["status"] == "failed" and "depends" in result["error"]
    assert client.get(f"/api/files/{fid}/editor").json()["revision"] == 2


def test_advanced_preview_recovery_and_background_export(client):
    fid, _ = upload(client)
    response = client.post(f"/api/files/{fid}/preview-cleaning?background=true",json={"operations": []})
    assert response.status_code == 200
    key = response.json()["job_id"]
    for _ in range(200):
        rate.clear()
        status = client.get(f"/api/jobs/{key}").json()
        if status["status"] == "completed":break
        time.sleep(.01)
    assert status["status"] == "completed"
    store.jobs.clear()  # Completed results survive service-memory loss.
    assert client.get(f"/api/jobs/{key}/results").json()["after"]["rows"][0][0] == "001"
    clean_key = client.post(f"/api/files/{fid}/clean",json={"operations": []}).json()["job_id"]
    for _ in range(200):
        rate.clear()
        status = client.get(f"/api/jobs/{clean_key}").json()
        if status["status"] == "completed":break
        time.sleep(.01)
    export_key = job(client,fid,0,"export",format="report",source_job=clean_key)
    export_status=wait(client,export_key)
    assert export_status["status"] == "completed", export_status
    assert client.get(export_status["result"]["download"]).content.startswith(b"%PDF")
    assert client.delete(f"/api/files/{fid}").status_code == 200
    assert client.get(export_status["result"]["download"]).status_code == 404
    assert client.get(f"/api/jobs/{clean_key}/results").status_code == 404


def test_recipe_imputation_recalculates_per_destination(client):
    first,_=upload(client,b"Amount\n10\n30\nNA\n")
    choice=wait(client,job(client,first,0,"decision",decision={"kind":"missing_markers","column":"Amount","settings":{"convert":True}}))
    assert choice["status"]=="completed",choice
    body={"revision":1,"column":"Amount","row_index":2,"scope":"column","action":"impute_missing_values","parameters":{"method":"mean","confirmed":True}}
    assert wait(client,job(client,first,1,"decision",decision={"kind":"fix","body":body}))["status"]=="completed"
    recipe=client.get(f"/api/files/{first}/workflow/recipe").json()
    other,_=upload(client,b"Amount\n100\n300\nNA\n")
    result=wait(client,job(client,other,0,"recipe",recipe=recipe))
    assert result["status"]=="completed",result
    rows=client.get(f"/api/files/{other}/editor").json()["preview"]["rows"]
    from decimal import Decimal
    assert Decimal(str(rows[2][0])) == Decimal("200")


def test_incremental_profile_matches_full_and_updates_cross_column_duplicates(monkeypatch):
    import copy
    import app.core.profiler as profiler
    frame = pd.DataFrame({"City": ["Cairo", "Cairo", "Giza"], "Amount": ["1", "2", "3"]})
    record = {"editor_df": frame, "editor_revision": 0}
    profile_record(record)
    apply_decision(record, {"kind":"fix", "body":{"revision":0,"column":"Amount","row_index":1,"scope":"cell","action":"replace","value":"1"}})
    full = copy.deepcopy(record)
    full.pop("workflow_raw_profile", None)
    full.pop("workflow_annotations", None)
    original = profiler.profile_column
    seen = []
    def counted(series):
        seen.append(series.name)
        return original(series)
    monkeypatch.setattr(profiler, "profile_column", counted)
    profile_record(record)
    assert seen == ["Amount"]
    assert any(issue["kind"] == "duplicate" for issue in record["workflow_annotations"]["City"][1])
    profile_record(full)
    assert record["editor_profile"] == full["editor_profile"]
    assert record["workflow_annotations"] == full["workflow_annotations"]


def test_lightweight_job_access_keeps_owner_and_expiry_checks(client):
    fid, _ = upload(client)
    session = client.cookies.get("dataneat_session")
    store.check_access(fid, session)
    with pytest.raises(KeyError): store.check_access(fid, "another-session")
    record = store.get(fid, session)
    record["created"] = time.time() - 86401
    store.save(record)
    with pytest.raises(KeyError): store.check_access(fid, session)

def test_integrated_plan_uses_current_sheet_and_failed_plan_is_atomic(client):
    fid, initial = upload(client, b"City,Amount\nCairo,10\nKairo,20\n")
    edit = {"kind":"fix","body":{"revision":0,"column":"City","row_index":1,"scope":"cell","action":"replace","value":"Alexandria"}}
    assert wait(client, job(client,fid,0,"decision",decision=edit))["status"] == "completed"
    steps = [{"kind":"fix","body":{"revision":1,"column":"City","row_index":0,"scope":"column","action":"normalize_capitalization","parameters":{"strategy":"upper"}}}]
    preview = wait(client,job(client,fid,1,"plan_preview",steps=steps))
    assert preview["status"] == "completed", preview
    assert preview["result"]["operations"][0]["examples"][1]["before"] == "Alexandria"
    assert client.get(f"/api/files/{fid}/editor").json()["revision"] == 1
    failed = wait(client,job(client,fid,1,"plan",steps=steps+[{"kind":"rename","column":"City","settings":{"name":"Amount"}}]))
    assert failed["status"] == "failed", failed
    unchanged = client.get(f"/api/files/{fid}/editor").json()
    assert unchanged["revision"] == 1 and unchanged["preview"]["rows"][1][0] == "Alexandria"
    assert wait(client,job(client,fid,1,"plan",steps=steps))["status"] == "completed"
    updated = client.get(f"/api/files/{fid}/editor").json()
    assert updated["preview"]["rows"][1][0] == "ALEXANDRIA"
    assert updated["revision"] == 2


def test_rename_preserves_rules_undo_and_recipe(client):
    fid, _ = upload(client,b"City,Amount\nCairo,10\nGiza,20\n")
    assert wait(client,job(client,fid,0,"decision",decision={"kind":"rules","column":"City","settings":{"required":True}}))["status"] == "completed"
    result=wait(client,job(client,fid,1,"plan",steps=[{"kind":"rename","column":"City","settings":{"name":"Location"}}]))
    assert result["status"] == "completed", result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["columns"] == ["Location","Amount"]
    settings=client.get(f"/api/files/{fid}/workflow/settings").json()
    assert settings["rules"]["Location"]["required"]
    assert settings["recipe"]["steps"][-1]["kind"] == "rename"
    assert client.get(f"/api/files/{fid}/workflow/changes").json()["rows"][-1]["spreadsheet_row"] == 1
    undone=wait(client,job(client,fid,current["revision"],"undo",step_id=current["changes"][-1]["id"]))
    assert undone["status"] == "completed", undone
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["columns"] == ["City","Amount"]
    assert client.get(f"/api/files/{fid}/workflow/settings").json()["rules"]["City"]["required"]


def test_integrated_plan_currency_percentage_and_imputation_audit(client):
    fid, _=upload(client,b"Amount,Rate\n10,10%\n20,20%\n,30%\n")
    steps=[{"kind":"fix","body":{"revision":0,"column":"Amount","row_index":0,"scope":"column","action":"impute_missing_values","parameters":{"method":"median","confirmed":True}}},
           {"kind":"fix","body":{"revision":0,"column":"Rate","row_index":0,"scope":"column","action":"normalize_percentage","parameters":{"action":"legacy","format":"ratio","bare_interpretation":"preserve"}}}]
    result=wait(client,job(client,fid,0,"plan_preview",steps=steps))
    assert result["status"] == "completed",result
    assert result["result"]["operations"][0]["imputation"]["imputed_count"] == 1
    assert wait(client,job(client,fid,0,"plan",steps=steps))["status"] == "completed"
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["is_imputed"][2][0] is True
    assert current["preview"]["is_imputed"][0][0] is False
    assert float(current["preview"]["rows"][2][0]) == 15
    assert float(current["preview"]["rows"][0][1]) == .1
    correction={"kind":"fix","body":{"revision":2,"column":"Amount","row_index":2,"scope":"cell","action":"replace","value":"21"}}
    assert wait(client,job(client,fid,2,"decision",decision=correction))["status"] == "completed"
    corrected=client.get(f"/api/files/{fid}/editor").json()
    assert corrected["preview"]["is_imputed"][2][0] is False
    assert wait(client,job(client,fid,3,"undo",step_id=corrected["changes"][-1]["id"]))["status"] == "completed"
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["is_imputed"][2][0] is True
    assert wait(client,job(client,fid,4,"decision",decision={"kind":"rename","column":"Amount","settings":{"name":"Total"}}))["status"] == "completed"
    renamed=client.get(f"/api/files/{fid}/editor").json()
    assert renamed["preview"]["columns"][0] == "Total" and renamed["preview"]["is_imputed"][2][0] is True


def test_plan_duplicate_subset_and_invalid_dates(client):
    fid,_=upload(client,b"City,Date\nCairo,2020-01-01\nCairo,2021-01-01\nGiza,2025-99-88\n")
    steps=[{"kind":"fix","body":{"revision":0,"column":"Date","row_index":0,"scope":"column","action":"resolve_invalid_dates","parameters":{"action":"empty"}}},
           {"kind":"fix","body":{"revision":0,"column":"City","row_index":0,"scope":"column","action":"remove_duplicates","parameters":{"subset":["City"]}}}]
    result=wait(client,job(client,fid,0,"plan",steps=steps))
    assert result["status"] == "completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["total_rows"] == 2
    assert current["preview"]["rows"][1][1] is None

def test_manual_placeholder_is_accepted_only_in_changed_cell_and_undo_restores_issue(client):
    fid,_=upload(client,b"Email\na@example.com\nb@example.com\nc@example.com\nd@example.com\nbad-email\nother-bad\n")
    edit={"kind":"fix","body":{"revision":0,"column":"Email","row_index":4,"scope":"cell","action":"replace","value":"No Email Provided"}}
    assert wait(client,job(client,fid,0,"decision",decision=edit))["status"] == "completed"
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][4][0] == "No Email Provided"
    assert current["preview"]["cell_issues"][4][0] == []
    assert current["preview"]["cell_issues"][5][0]
    assert wait(client,job(client,fid,1,"analysis"))["status"] == "completed"
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["cell_issues"][4][0] == []
    current=client.get(f"/api/files/{fid}/editor").json()
    assert wait(client,job(client,fid,current["revision"],"undo",step_id=current["changes"][-1]["id"]))["status"] == "completed"
    undone=client.get(f"/api/files/{fid}/editor").json()
    assert undone["preview"]["rows"][4][0] == "bad-email" and undone["preview"]["cell_issues"][4][0]


def test_bulk_entered_values_accepted_and_rename_preserves_acceptance(client):
    fid,_=upload(client,b"Email\na@example.com\nb@example.com\nc@example.com\nd@example.com\nbad-email\nbad-email\nother-bad\n")
    edit={"kind":"fix","body":{"revision":0,"column":"Email","row_index":4,"scope":"matching","action":"replace","value":"No Email Provided"}}
    assert wait(client,job(client,fid,0,"decision",decision=edit))["status"] == "completed"
    assert wait(client,job(client,fid,1,"decision",decision={"kind":"rename","column":"Email","settings":{"name":"Contact"}}))["status"] == "completed"
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["cell_issues"][4][0] == [] and current["preview"]["cell_issues"][5][0] == []
    assert current["preview"]["cell_issues"][6][0]


def test_existing_entered_placeholder_is_accepted_on_workspace_upgrade(client):
    fid,_=upload(client,b"Email\na@example.com\nb@example.com\nc@example.com\nd@example.com\nbad-email\n")
    edit={"kind":"fix","body":{"revision":0,"column":"Email","row_index":4,"scope":"cell","action":"replace","value":"No Email Provided"}}
    assert wait(client,job(client,fid,0,"decision",decision=edit))["status"] == "completed"
    with store.lock:
        record=store.get(fid,client.cookies.get("dataneat_session"))
        record.pop("manual_acceptance_version",None)
        record["workflow_annotations"]["Email"][4]=[{"kind":"email","message":"Invalid email","classification":"invalid"}]
        store.save(record)
    restored=client.post(f"/api/files/{fid}/workflow/init")
    assert restored.status_code == 200, restored.text
    assert restored.json()["revision"] == 1 and restored.json()["preview"]["cell_issues"][4][0] == []

@pytest.mark.parametrize("output,expected",[("true_false",[True,False,True]),("yes_no",["Yes","No","Yes"]),("one_zero",["1","0","1"])])
def test_boolean_output_choices_preserve_unknown_values(client,output,expected):
    fid,_=upload(client,b"Active\nY\nno\nTRUE\nunknown\n")
    decision={"kind":"fix","body":{"revision":0,"column":"Active","row_index":0,"scope":"column","action":"normalize_boolean","parameters":{"format":output}}}
    result=wait(client,job(client,fid,0,"decision",decision=decision))
    assert result["status"] == "completed",result
    rows=client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"]
    assert [row[0] for row in rows[:3]] == expected
    assert rows[3][0] == "unknown"


def test_survey_plan_preview_skip_semantics_and_selected_changes(client):
    fid,_=upload(client,b'ID,City,Active,Email,Date\n001," Cairo ",Y,N/A,13/09/2021\n002,Giza,TRUE,b@example.com,2020-01-01\n003,Mansoura,0,c@example.com,2020-02-03\nN/A,Tanta,no,null,2020-03-04\n')
    steps=[{"kind":"rules","column":"ID","settings":{"type":"identifier"}},
           {"kind":"preparation","settings":{"trim":True,"collapse":False,"normalize_missing":True,"markers":["","N/A"],"columns":{"ID":{"excluded":True}}}},
           {"kind":"fix","body":{"revision":0,"column":"Active","row_index":0,"scope":"column","action":"normalize_boolean","parameters":{"format":"yes_no"}}},
           {"kind":"fix","body":{"revision":0,"column":"Date","row_index":0,"scope":"column","action":"normalize_dates","parameters":{"interpretation":"day_first"}}},
           {"kind":"ignore","column":"Email","row_index":3,"value":"null","issue":"*","reason":"Reviewed placeholder intentionally retained as text."},
           {"kind":"fix","body":{"revision":0,"column":"Email","row_index":0,"scope":"column","action":"impute_missing_values","parameters":{"method":"constant","value":"No Email Provided","confirmed":True}}}]
    preview=wait(client,job(client,fid,0,"plan_preview",steps=steps))
    assert preview["status"] == "completed",preview
    unchanged=client.get(f"/api/files/{fid}/editor").json()
    assert unchanged["revision"] == 0 and unchanged["changes"] == []
    assert unchanged["preview"]["rows"][0] == ["001"," Cairo ","Y","N/A","13/09/2021"]
    applied=wait(client,job(client,fid,0,"plan",steps=steps))
    assert applied["status"] == "completed",applied
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0] == ["001","Cairo","Yes","No Email Provided","2021-09-13"]
    assert current["preview"]["rows"][3][0] == "N/A"
    assert current["preview"]["rows"][3][3] == "null"
    assert current["preview"]["total_rows"] == 4 and len(current["changes"]) == 6
    assert current["preview"]["cell_issues"][0][3] == []
    assert current["preview"]["is_imputed"][0][3] is False
    visible_email_errors = sum(item["kind"] == "email" for row in current["preview"]["cell_issues"] for item in row[3])
    assert sum(issue["count"] for c in current["profile"]["columns"] if c["column_name"] == "Email" for issue in c["issues"] if issue["issue"] == "invalid_email") == visible_email_errors


def test_optional_automatic_survey_applies_current_copy_and_is_undoable(client):
    fid, initial = upload(client, b"ID,City,Active,Amount\n001, cairo ,Y,10\n002,GIZA,TRUE,30\n003,tanta,0,\n004,mansoura,no,50\n")
    assert initial["revision"] == 0
    result = wait(client, job(client, fid, 0, "automatic", answers={"trim":True,"boolean":"yes_no","capitalization":"title","missing":"median"}))
    assert result["status"] == "completed", result
    current = client.get(f"/api/files/{fid}/editor").json()
    rows = current["preview"]["rows"]
    assert rows[0][:3] == ["001", "Cairo", "Yes"]
    assert rows[2][2] == "No"
    assert float(rows[2][3]) == 30
    assert current["changes"]
    last = current["changes"][-1]
    undone = wait(client, job(client, fid, current["revision"], "undo", step_id=last["id"]))
    assert undone["status"] == "completed", undone


def test_automatic_unanswered_preserves_values_and_validates_answers(client):
    fid, initial = upload(client)
    result = wait(client, job(client, fid, 0, "automatic", answers={"trim":False}))
    assert result["status"] == "completed", result
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"] == initial["preview"]["rows"]
    response = client.post(f"/api/files/{fid}/workflow/jobs",json={"revision":0,"operation":"automatic","answers":{"missing":"guess"}})
    assert response.status_code == 422


def test_automatic_preserves_manual_corrections(client):
    fid, _ = upload(client)
    result = wait(client, job(client, fid, 0, "decision", decision={"kind":"fix","body":{"revision":0,"column":"City","row_index":0,"scope":"cell","action":"replace","value":"my PLACE"}}))
    assert result["status"] == "completed", result
    result = wait(client, job(client, fid, 1, "automatic",answers={"capitalization":"upper"}))
    assert result["status"] == "completed", result
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"][0][1] == "my PLACE"
    assert any("City:" in value for value in result["result"]["skipped"])



def test_automatic_column_exceptions_override_only_selected_policies(client):
    csv = b"City,Department,Other,Active,Verified,Join_Date,Review_Date,Amount,Cost\n cairo , SALES , Mixed ,Y,TRUE,13/09/2021,14/09/2021,10,10\n GIZA , HR , Text ,TRUE,Y,2020-01-01,2020-01-01,30,30\n tanta , IT , More ,0,no,2020-02-03,2020-02-03,,\n mansoura , FINANCE , Case ,no,0,2020-03-04,2020-03-04,50,50\n"
    fid, _ = upload(client, csv)
    answers={"trim":True,"boolean":"yes_no","capitalization":"title","dates":"unambiguous","missing":"median","exceptions":{"Department":{"capitalization":"lower"},"Other":{"trim":False,"capitalization":"preserve"},"Verified":{"boolean":"one_zero"},"Review_Date":{"dates":"preserve"},"Cost":{"missing":"preserve"}}}
    result = wait(client, job(client, fid, 0, "automatic", answers=answers))
    assert result["status"] == "completed", result
    rows = client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"]
    assert rows[0][:5] == ["Cairo","sales"," Mixed ","Yes","1"]
    assert rows[0][5:7] == ["2021-09-13","14/09/2021"]
    assert float(rows[2][7]) == 30
    assert rows[2][8] in (None, "")


def test_automatic_exception_can_enable_policy_when_general_is_preserve(client):
    fid, _ = upload(client, b"City,Department\ncairo,SALES\ngiza,FINANCE\ntanta,IT\n")
    result = wait(client, job(client, fid, 0, "automatic", answers={"trim":False,"exceptions":{"City":{"capitalization":"upper"}}}))
    assert result["status"] == "completed", result
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"][0] == ["CAIRO","SALES"]


def test_automatic_exception_unknown_column_is_atomic_and_bad_policy_rejected(client):
    fid, before = upload(client)
    result = wait(client, job(client, fid, 0, "automatic", answers={"exceptions":{"MissingColumn":{"trim":False}}}))
    assert result["status"] == "failed", result
    assert "MissingColumn" in result["error"]
    after = client.get(f"/api/files/{fid}/editor").json()
    assert after["revision"] == 0 and after["preview"]["rows"] == before["preview"]["rows"]
    response = client.post(f"/api/files/{fid}/workflow/jobs",json={"revision":0,"operation":"automatic","answers":{"exceptions":{"City":{"capitalization":"random"}}}})
    assert response.status_code == 422


def test_affected_rows_filter_spans_pages_and_keeps_original_row_identity(client):
    lines = ["ID,City"] + [f"{index:03d}," + (" Cairo " if index in (2,29,38) else "Cairo") for index in range(1,41)]
    fid, initial = upload(client, ("\n".join(lines)+"\n").encode())
    response = client.get(f"/api/files/{fid}/editor?affected_only=true&issue_column=City&issue_kind=whitespace&page_size=2")
    assert response.status_code == 200, response.text
    filtered=response.json()
    assert filtered["preview"]["total_rows"] == 3
    assert filtered["preview"]["row_indices"] == [1,28]
    assert filtered["overview"]["cells"] == 3
    second=client.get(f"/api/files/{fid}/editor?affected_only=true&issue_column=City&issue_kind=whitespace&page_size=2&page=2").json()
    assert second["preview"]["row_indices"] == [37]
    empty=client.get(f"/api/files/{fid}/editor?affected_only=true&issue_column=City&issue_kind=invalid_date").json()
    assert empty["preview"]["rows"] == [] and empty["preview"]["total_rows"] == 0
    assert client.get(f"/api/files/{fid}/editor?affected_only=true&issue_column=Absent").status_code == 422
    counts=client.get(f"/api/files/{fid}/editor/scope-counts?column=City&row_index=1&kind=whitespace").json()
    assert counts == {"cell":1,"matching":3,"issue":3,"column":40}


def test_undo_automatic_run_preserves_later_manual_and_other_runs(client):
    fid, _ = upload(client, b"ID,City,Department\n001, cairo ,SALES\n002,giza,FINANCE\n003,tanta,IT\n")
    first=wait(client,job(client,fid,0,"automatic",answers={"capitalization":"title"}))
    assert first["status"] == "completed", first
    current=client.get(f"/api/files/{fid}/editor").json()
    first_id=first["result"]["run_id"]
    assert current["automatic_runs"] == [first_id]
    assert first["result"]["remaining"]["cells"] == 0
    manual=wait(client,job(client,fid,current["revision"],"decision",decision={"kind":"fix","body":{"revision":current["revision"],"column":"ID","row_index":0,"scope":"cell","action":"replace","value":"CUSTOM-ID"}}))
    assert manual["status"] == "completed", manual
    current=client.get(f"/api/files/{fid}/editor").json()
    second=wait(client,job(client,fid,current["revision"],"automatic",answers={"trim":False,"capitalization":"upper"}))
    assert second["status"] == "completed", second
    current=client.get(f"/api/files/{fid}/editor").json()
    # Removing a single step must keep run identity on the surviving decisions.
    undone_step=wait(client,job(client,fid,current["revision"],"undo",step_id=current["changes"][-1]["id"]))
    assert undone_step["status"] == "completed", undone_step
    current=client.get(f"/api/files/{fid}/editor").json()
    assert first_id in current["automatic_runs"]
    result=wait(client,job(client,fid,current["revision"],"undo_run",run_id=first_id))
    assert result["status"] == "completed", result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0][0] == "CUSTOM-ID"
    assert first_id not in current["automatic_runs"]
    assert current["automatic_runs"] == [second["result"]["run_id"]]
    assert current["preview"]["rows"][0][1] == " CAIRO "
    failed=wait(client,job(client,fid,current["revision"],"undo_run",run_id=first_id))
    assert failed["status"] == "failed"


@pytest.mark.parametrize("operation", ["undo", "undo_run"])
def test_undo_rebuilds_issue_annotations_before_replaying_accepted_replacements(client, operation):
    fid, _ = upload(client, b"ID,Name,Salary,Email,City\n001, ALICE SMITH ,,invalid-email, Cairo \n002,bob jones,10,b@example.com,Giza\n003,carol jane,30,c@example.com,Tanta\n")
    run=wait(client,job(client,fid,0,"automatic",answers={"capitalization":"title","exceptions":{"City":{"trim":False,"capitalization":"preserve"},"Email":{"capitalization":"preserve"}}}))
    assert run["status"] == "completed", run
    for column, kind, value in [("Salary","missing","Not provided"),("Email","email","No email provided")]:
        current=client.get(f"/api/files/{fid}/editor").json()
        decision={"kind":"fix","body":{"revision":current["revision"],"column":column,"row_index":0,"scope":"issue","action":"replace","value":value,"parameters":{"issue_kind":kind}}}
        done=wait(client,job(client,fid,current["revision"],"decision",decision=decision))
        assert done["status"] == "completed", done
    current=client.get(f"/api/files/{fid}/editor").json()
    done=wait(client,job(client,fid,current["revision"],"decision",decision={"kind":"fix","body":{"revision":current["revision"],"column":"City","row_index":0,"scope":"column","action":"trim_whitespace"}}))
    assert done["status"] == "completed", done
    current=client.get(f"/api/files/{fid}/editor").json()
    result=wait(client,job(client,fid,current["revision"],operation,**({"step_id":current["changes"][-1]["id"]} if operation=="undo" else {"run_id":run["result"]["run_id"]})))
    assert result["status"] == "completed", result
    after=client.get(f"/api/files/{fid}/editor").json()
    assert after["preview"]["rows"][0][2:4] == ["Not provided","No email provided"]
    assert after["preview"]["rows"][0][1] == ("Alice Smith" if operation=="undo" else " ALICE SMITH ")
    assert after["preview"]["rows"][0][4] == (" Cairo " if operation=="undo" else "Cairo")


def test_missing_labels_require_choice_and_real_blanks_are_distinct(client):
    fid, initial=upload(client,b"ID,Phone\n001,NA\n002,null\n003,empty\n004,\n005,01252578740\n006,N/A\n")
    phone=next(c for c in initial["profile"]["columns"] if c["column_name"]=="Phone")
    assert phone["missing_count"] == 1
    assert phone["missing_marker_review"]["count"] == 4
    assert initial["preview"]["rows"][0][1] == "NA"
    assert [i["kind"] for i in initial["preview"]["cell_issues"][0][1]] == ["missing_marker"]
    assert any(i["kind"]=="missing" for i in initial["preview"]["cell_issues"][3][1])
    result=wait(client,job(client,fid,0,"automatic",answers={"missing":"median","capitalization":"lower"}))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"] == initial["preview"]["rows"]
    assert any("Phone:" in item for item in result["result"]["skipped"])
    result=wait(client,job(client,fid,current["revision"],"decision",decision={"kind":"missing_markers","column":"Phone","settings":{"convert":True}}))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert [row[1] for row in current["preview"]["rows"]] == [None,None,None,"","01252578740",None]
    assert next(c for c in current["profile"]["columns"] if c["column_name"]=="Phone")["missing_count"] == 5
    reverted=wait(client,job(client,fid,current["revision"],"undo",step_id=current["changes"][-1]["id"]))
    assert reverted["status"]=="completed",reverted
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"]==initial["preview"]["rows"]
    assert next(c for c in current["profile"]["columns"] if c["column_name"]=="Phone")["missing_marker_review"]["count"]==4


def test_keep_missing_labels_as_literal_text_is_column_specific_and_undoable(client):
    fid, initial=upload(client,b"City,Region\nNA,NA\nCairo,null\nempty,Giza\n")
    result=wait(client,job(client,fid,0,"decision",decision={"kind":"missing_markers","column":"City","settings":{"convert":False}}))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    cols={c["column_name"]:c for c in current["profile"]["columns"]}
    assert cols["City"]["missing_count"]==0 and cols["City"]["missing_marker_review"]["count"]==0
    assert cols["Region"]["missing_marker_review"]["count"]==2
    assert current["preview"]["rows"]==initial["preview"]["rows"]
    result=wait(client,job(client,fid,current["revision"],"undo",step_id=current["changes"][-1]["id"]))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert next(c for c in current["profile"]["columns"] if c["column_name"]=="City")["missing_marker_review"]["count"]==2


def test_existing_workflow_upgrades_missing_labels_without_reverting_user_data(client):
    fid, _=upload(client,b"Name,Phone\nAlice,NA\nBob,01234567890\n")
    edit={"kind":"fix","body":{"revision":0,"column":"Name","row_index":0,"scope":"cell","action":"replace","value":"Custom Name"}}
    assert wait(client,job(client,fid,0,"decision",decision=edit))["status"]=="completed"
    record=store.get(fid,client.cookies.get("dataneat_session"))
    record.pop("missing_marker_review_version",None)
    record["_workflow_dirty"]=list(record["editor_df"].columns)
    profile_record(record)
    store.save(record)
    result=client.post(f"/api/files/{fid}/workflow/init")
    assert result.status_code==200,result.text
    current=result.json()
    assert current["revision"]==1
    assert current["preview"]["rows"][0]==["Custom Name","NA"]
    assert next(c for c in current["profile"]["columns"] if c["column_name"]=="Phone")["missing_marker_review"]["count"]==1


@pytest.mark.parametrize("output,expected",[("YYYY-MM-DD","2021-05-06"),("DD/MM/YYYY","06/05/2021"),("MM/DD/YYYY","05/06/2021"),("YYYY/MM/DD","2021/05/06"),("DD-MM-YYYY","06-05-2021"),("MM-DD-YYYY","05-06-2021")])
def test_date_output_formats_preserve_calendar_meaning(client,output,expected):
    fid,_=upload(client,b"Event_Date\n2021-05-06\n13/09/2021\n04/07/2020\n2025-99-88\n")
    decision={"kind":"fix","body":{"revision":0,"column":"Event_Date","row_index":0,"scope":"column","action":"normalize_dates","parameters":{"interpretation":"preserve","output_format":output}}}
    result=wait(client,job(client,fid,0,"decision",decision=decision))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0][0]==expected
    assert current["preview"]["rows"][2][0]=="04/07/2020" # unresolved input is preserved
    assert current["preview"]["rows"][3][0]=="2025-99-88"
    assert not any(flag["kind"] in ("ambiguous_date","date_format") for flag in current["preview"]["cell_issues"][0][0])


def test_reformat_known_slash_dates_and_undo_keeps_day_month_order(client):
    fid,_=upload(client,b"Event_Date\n2021-05-06\n2021-09-13\n2021-12-04\n")
    def standardize(revision, output):
        return wait(client,job(client,fid,revision,"decision",decision={"kind":"fix","body":{"revision":revision,"column":"Event_Date","row_index":0,"scope":"column","action":"normalize_dates","parameters":{"interpretation":"preserve","output_format":output}}}))
    first=standardize(0,"DD/MM/YYYY")
    assert first["status"]=="completed",first
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0][0]=="06/05/2021"
    second=standardize(current["revision"],"MM/DD/YYYY")
    assert second["status"]=="completed",second
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0][0]=="05/06/2021"
    assert current["preview"]["rows"][1][0]=="09/13/2021"
    assert not any(flag["kind"] in ("ambiguous_date","date_format") for row in current["preview"]["cell_issues"] for flags in row for flag in flags)
    undone=wait(client,job(client,fid,current["revision"],"undo",step_id=current["changes"][-1]["id"]))
    assert undone["status"]=="completed",undone
    assert client.get(f"/api/files/{fid}/editor").json()["preview"]["rows"][0][0]=="06/05/2021"


@pytest.mark.parametrize("interpretation,output,expected_iso",[("day_first","DD/MM/YYYY","2024-02-01"),("month_first","MM/DD/YYYY","2024-01-02")])
def test_same_text_date_interpretation_preview_apply_and_undo(client,interpretation,output,expected_iso):
    fid,initial=upload(client,b"Event_Date\n01/02/2024\n02/02/2024\n03/02/2024\n2024-99-88\n")
    body={"revision":0,"column":"Event_Date","row_index":0,"scope":"column","action":"normalize_dates","parameters":{"interpretation":interpretation,"output_format":output}}
    preview=client.post(f"/api/files/{fid}/editor/fix",json=body)
    assert preview.status_code==200,preview.text
    assert preview.json()["proposal"]["changed_cells"]==0
    assert preview.json()["proposal"]["interpreted_dates"]==2
    # Preview records no decision and leaves original ambiguity visible.
    unchanged=client.get(f"/api/files/{fid}/editor").json()
    assert unchanged["revision"]==0
    assert any(flag["kind"]=="ambiguous_date" for flag in unchanged["preview"]["cell_issues"][0][0])
    applied=wait(client,job(client,fid,0,"decision",decision={"kind":"fix","body":body}))
    assert applied["status"]=="completed",applied
    assert applied["result"]["proposal"]["interpreted_dates"]==2
    current=client.get(f"/api/files/{fid}/editor").json()
    confirmation=current["changes"][-1]
    assert current["preview"]["rows"]==initial["preview"]["rows"]
    assert confirmation["changed_cells"]==0 and confirmation["interpreted_dates"]==2
    assert not any(flag["kind"]=="ambiguous_date" for row in current["preview"]["cell_issues"] for cell in row for flag in cell)
    assert any(flag["kind"]=="invalid_date" for flag in current["preview"]["cell_issues"][3][0])
    # Repeating a confirmed interpretation is a real no-op.
    body["revision"]=1
    repeated=client.post(f"/api/files/{fid}/editor/fix",json=body).json()["proposal"]
    assert repeated["changed_cells"]==0 and repeated["interpreted_dates"]==0
    # A later reformat uses the confirmed meaning instead of guessing again.
    body["parameters"]={"interpretation":"preserve","output_format":"YYYY-MM-DD"}
    reformatted=wait(client,job(client,fid,1,"decision",decision={"kind":"fix","body":body}))
    assert reformatted["status"]=="completed",reformatted
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0][0]==expected_iso
    assert wait(client,job(client,fid,2,"undo",step_id=current["changes"][-1]["id"]))["status"]=="completed"
    assert wait(client,job(client,fid,3,"undo",step_id=confirmation["id"]))["status"]=="completed"
    restored=client.get(f"/api/files/{fid}/editor").json()
    assert restored["preview"]["rows"]==initial["preview"]["rows"]
    assert any(flag["kind"]=="ambiguous_date" for flag in restored["preview"]["cell_issues"][0][0])


def test_same_text_date_confirmation_requires_explicit_interpretation_and_respects_cell_scope(client):
    fid,_=upload(client,b"Event_Date\n01/02/2024\n03/02/2024\n13/02/2024\n")
    body={"revision":0,"column":"Event_Date","row_index":0,"scope":"cell","action":"normalize_dates","parameters":{"interpretation":"preserve","output_format":"DD/MM/YYYY"}}
    proposal=client.post(f"/api/files/{fid}/editor/fix",json=body).json()["proposal"]
    assert proposal["changed_cells"]==0 and proposal["interpreted_dates"]==0
    body["parameters"]["interpretation"]="day_first"
    proposal=client.post(f"/api/files/{fid}/editor/fix",json=body).json()["proposal"]
    assert proposal["changed_cells"]==0 and proposal["interpreted_dates"]==1
    assert wait(client,job(client,fid,0,"decision",decision={"kind":"fix","body":body}))["status"]=="completed"
    current=client.get(f"/api/files/{fid}/editor").json()
    assert not any(flag["kind"]=="ambiguous_date" for flag in current["preview"]["cell_issues"][0][0])
    assert any(flag["kind"]=="ambiguous_date" for flag in current["preview"]["cell_issues"][1][0])


@pytest.mark.parametrize("interpretation,output,expected",[("day_first","DD/MM/YYYY","02/02/2024"),("month_first","MM/DD/YYYY","02/01/2024")])
def test_same_text_date_interpretation_is_used_by_later_date_median(client,interpretation,output,expected):
    fid,_=upload(client,b"Event_Date,Row\n01/02/2024,1\n03/02/2024,2\n,3\n")
    body={"revision":0,"column":"Event_Date","row_index":0,"scope":"column","action":"normalize_dates","parameters":{"interpretation":interpretation,"output_format":output}}
    assert wait(client,job(client,fid,0,"decision",decision={"kind":"fix","body":body}))["status"]=="completed"
    body.update(revision=1,row_index=2,action="impute_missing_values",parameters={"method":"median","date_rounding":"floor","date_estimate_acknowledged":True})
    result=wait(client,job(client,fid,1,"decision",decision={"kind":"fix","body":body}))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][2][0]==expected
    assert current["preview"]["is_imputed"][2][0]


def test_automatic_date_output_exception_and_recipe(client):
    fid,_=upload(client,b"Start_Date,End_Date\n2021-05-06,2021-06-07\n2021-09-13,2021-09-14\n")
    result=wait(client,job(client,fid,0,"automatic",answers={"dates":"unambiguous","date_output":"DD/MM/YYYY","exceptions":{"End_Date":{"date_output":"YYYY/MM/DD"}}}))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0]==["06/05/2021","2021/06/07"]
    recipe=client.get(f"/api/files/{fid}/workflow/recipe").json()
    other,_=upload(client,b"Start_Date,End_Date\n2022-03-04,2022-04-05\n2022-09-13,2022-09-14\n")
    applied=wait(client,job(client,other,0,"recipe",recipe=recipe))
    assert applied["status"]=="completed",applied
    assert client.get(f"/api/files/{other}/editor").json()["preview"]["rows"][0]==["04/03/2022","2022/04/05"]


def test_date_output_rejects_invalid_formats_and_preserves_datetime_offset(client):
    fid,_=upload(client,b"Event_Date\n2021-05-06T08:30:00+02:00\n2021-09-13T10:15:00+02:00\n")
    body={"revision":0,"column":"Event_Date","row_index":0,"scope":"column","action":"normalize_dates","parameters":{"include_time":True,"output_format":"DD/MM/YYYY"}}
    result=wait(client,job(client,fid,0,"decision",decision={"kind":"fix","body":body}))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"][0][0]=="06/05/2021T08:30:00+02:00"
    assert current["profile"]["columns"][0]["detected_type"]=="datetime"
    assert not any(flag["kind"]=="invalid_date" for row in current["preview"]["cell_issues"] for flags in row for flag in flags)
    for bad in ("custom %Y",["DD/MM/YYYY"]):
        body["revision"]=1;body["parameters"]["output_format"]=bad
        response=client.post(f"/api/files/{fid}/workflow/jobs",json={"revision":1,"operation":"decision","decision":{"kind":"fix","body":body}})
        assert response.status_code==422,response.text


@pytest.mark.parametrize("choice,expected_rows",[("preserve",4),("remove",3)])
def test_automatic_duplicate_rows_are_optional_and_undoable(client,choice,expected_rows):
    fid, initial=upload(client,b"ID,City,Amount\n001,Cairo,10\n001,Cairo,10\n002,Cairo,10\n003,Giza,20\n")
    result=wait(client,job(client,fid,0,"automatic",answers={"trim":False,"duplicates":choice}))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["total_rows"]==expected_rows
    assert result["result"]["removed_rows"]==(1 if choice=="remove" else 0)
    assert result["result"]["changed_cells"]==0
    if choice=="remove":
        assert current["preview"]["row_indices"]==[0,2,3]
        assert current["preview"]["rows"][1][0]=="002" # shared city/amount alone is not a duplicate
        assert current["changes"][-1]["action"]=="remove_duplicates"
        undone=wait(client,job(client,fid,current["revision"],"undo_run",run_id=result["result"]["run_id"]))
        assert undone["status"]=="completed",undone
        restored=client.get(f"/api/files/{fid}/editor").json()
        assert restored["preview"]["rows"]==initial["preview"]["rows"]


def test_automatic_removes_duplicates_after_selected_cleaning_and_exports_recipe(client):
    fid,_=upload(client,b"City,Amount\n Cairo ,10\nCairo,10\nGiza,20\n")
    result=wait(client,job(client,fid,0,"automatic",answers={"trim":True,"duplicates":"remove"}))
    assert result["status"]=="completed",result
    current=client.get(f"/api/files/{fid}/editor").json()
    assert current["preview"]["rows"]==[["Cairo","10"],["Giza","20"]]
    assert result["result"]["removed_rows"]==1
    assert result["result"]["changed_cells"]==1
    recipe=client.get(f"/api/files/{fid}/workflow/recipe").json()
    assert recipe["steps"][-1]["body"]["action"]=="remove_duplicates"
    bad=client.post(f"/api/files/{fid}/workflow/jobs",json={"revision":current["revision"],"operation":"automatic","answers":{"duplicates":"guess"}})
    assert bad.status_code==422

"""Bounded owner-scoped jobs, durable status, cooperative cancellation and CAS commits."""
import copy
import io
import json
import os
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from ..core.workflow import (Decision, Recipe, Preparation, ensure_workflow, apply_decision, replay_without, profile_record, recipe_from, compatible, apply_recipe, suggested_groups, diff, manual_acceptances)
from ..core.automatic_cleaning import AutomaticAnswers, automatic_steps
from ..core.common import scalar
from ..core.imputation_readiness import ANALYSIS_SCHEMA_VERSION, column_readiness
from ..core.pdf_report import cleaning_pdf


class JobInput(BaseModel):
    revision: int = Field(ge=0)
    operation: str = Field(pattern="^(decision|preview|undo|recipe|recipe_preview|export|analysis|plan|plan_preview|automatic|undo_run|quality_review)$")
    quality: dict = Field(default_factory=dict)
    steps: list[Decision] = Field(default_factory=list, max_length=100)
    decision: Decision | None = None
    recipe: Recipe | None = None
    step_id: str = ""
    run_id: str = ""
    format: str = Field(default="report", pattern="^(csv|xlsx|report|changes|package)$")
    include_changes: bool = False
    source_job: str = ""
    answers: AutomaticAnswers | None = None


class Cancelled(Exception):
    pass


def install_workflows(app, store, editor_response, safe_export):
    router = APIRouter(prefix="/api")
    pool = ThreadPoolExecutor(max_workers=int(os.getenv("CLEANING_WORKERS", "3")), thread_name_prefix="dataneat-workflow")
    jobs = {}
    lock = threading.RLock()
    def path(key):
        uuid.UUID(key)
        return store.root / (key + ".workflow-job")
    def persist(job):
        public = {k: v for k, v in job.items() if k not in ("cancel_event",)}
        target = path(job["id"]); temp = target.with_suffix(".job-tmp")
        temp.write_text(json.dumps(public, ensure_ascii=False, default=str), encoding="utf-8")
        os.chmod(temp, 0o600); temp.replace(target)
        os.utime(target, (job["created"], job["created"]))
    def get_job(key, session):
        with lock:
            job = jobs.get(key)
            if job is None:
                try: job = json.loads(path(key).read_text(encoding="utf-8"))
                except (OSError, ValueError): raise KeyError(key)
                if job["status"] in ("queued", "running"):
                    record = store.get(job["file_id"], session)
                    if record.get("last_workflow_job") == key:
                        job.update(status="completed", stage="Recovered committed revision", result={"revision": record["editor_revision"]})
                    else:
                        job.update(status="failed", error="The service restarted before completion. Your last committed revision is preserved; retry.")
                    persist(job)
            if job["session"] != session or time.time() - job["created"] > 86400:
                raise KeyError(key)
            # Access also ends when the parent upload is deleted or expires.
            store.check_access(job["file_id"], session)
            return job
    def update(job, **values):
        with lock:
            job.update(values); persist(job)
    def check(job):
        if job["cancel_event"].is_set() and not job.get("committed"): raise Cancelled()
    def commit(job, candidate, expected):
        with lock, store.lock:
            check(job)
            current = store.get(job["file_id"], job["session"])
            if current["editor_revision"] != expected:
                raise ValueError("The sheet changed while this job ran. No changes were committed; reload and retry.")
            candidate["last_workflow_job"] = job["id"]
            store.save(candidate)
            job["committed"] = True
    def export(record, body):
        fmt = body.format
        recipe = recipe_from(record, record.get("recipe_name", "My cleaning recipe"))
        if fmt == "changes":
            return json.dumps({"revision": record["editor_revision"], "coverage": record.get("legacy_history_notice") or "Complete for the enhanced workflow", "changes": record.get("complete_changes", []), "ignored_findings": record.get("ignored_findings", [])}, ensure_ascii=False, default=str).encode(), "application/json", "dataneat-changes.json"
        if fmt in ("report", "package"):
            preparation = ["Preparation was applied only through recorded, reviewed decisions.", f"Recipe: {record.get('recipe_name', 'None')} | Recipe version: {record.get('recipe_version', 'None')}"]
            if record.get("legacy_history_notice"): preparation.append(record["legacy_history_notice"])
            pdf = cleaning_pdf(record["filename"], record.get("editor_changes", []), record["profile"], record["editor_profile"], preparation, record["editor_revision"]).getvalue()
            if fmt == "report": return pdf, "application/pdf", "dataneat-cleaning-report.pdf"
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("report.pdf", pdf)
                archive.writestr("recipe.json", json.dumps(recipe, ensure_ascii=False))
                archive.writestr("README.txt", "Local review package. The PDF and recipe contain column names, selected values and before/after examples. The optional complete change log contains original and corrected cell values. Share only with authorized reviewers. The full original upload is NOT included. Recipe excludes row-specific corrections and ignored findings. PDF interface is English; Arabic PDF rendering is not offered.\n" + record.get("legacy_history_notice", ""))
                if body.include_changes:
                    archive.writestr("changes.json", json.dumps(record.get("complete_changes", []), ensure_ascii=False, default=str))
            return buffer.getvalue(), "application/zip", "dataneat-review-package.zip"
        df = record["editor_df"].map(safe_export)
        df.columns = [safe_export(str(c)) for c in df.columns]
        buffer = io.BytesIO()
        if fmt == "csv": buffer.write(df.to_csv(index=False).encode("utf-8-sig"))
        else: df.to_excel(buffer, index=False, engine="openpyxl")
        return buffer.getvalue(), "text/csv" if fmt == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"dataneat-cleaned.{fmt}"
    def run(job, record, body):
        try:
            check(job); update(job, status="running", stage="Preparing a separate working copy")
            # Store.get already supplied an isolated snapshot. Transformations copy
            # their DataFrame; a second deep copy duplicated the entire audit/history.
            candidate = record; ensure_workflow(candidate)
            if body.source_job:
                source = store.jobs.get(body.source_job) or store.load_job(body.source_job)
                if not source or source["session"] != job["session"] or source["file_id"] != job["file_id"] or source["status"] != "completed":
                    raise ValueError("Advanced results are not accessible in this session")
                candidate.update(editor_df=source["df"], editor_profile=source["validation"]["after"], editor_changes=source["operations"], workflow_steps=[], complete_changes=diff(record["df"], source["df"], "advanced_clean", 0, body.source_job, lambda: check(job)))
            result = {}
            if body.operation in ("decision", "preview"):
                if body.decision is None: raise ValueError("A decision is required")
                update(job, stage=f"Evaluating {body.decision.kind}")
                entry = apply_decision(candidate, body.decision.model_dump(), check=lambda: check(job))
                result = {"proposal": {**{k: entry[k] for k in ("changed_cells", "examples", "warnings")}, "interpreted_dates": entry.get("interpreted_dates", 0)}, "revision": candidate["editor_revision"]}
                if entry.get("quality"):
                    result["quality"] = entry["quality"]
            elif body.operation == "quality_review":
                from ..core.quality_tools import review
                update(job, stage="Analyzing the selected cleaning tool on the current working copy")
                result = review(candidate, body.quality, lambda: check(job))
                result["revision"] = candidate["editor_revision"]
            elif body.operation == "automatic":
                if body.answers is None: raise ValueError("Survey answers are required")
                update(job, stage="Analyzing every column in the current working copy")
                profile_record(candidate, lambda: check(job))
                steps, skipped = automatic_steps(candidate, body.answers)
                entries = []
                for number, step in enumerate(steps):
                    check(job)
                    update(job, stage=f"Automatic cleaning step {number + 1} of {len(steps)}", completed_units=number, total_units=len(steps))
                    if step["kind"] == "fix":
                        step["body"].update(revision=candidate["editor_revision"], row_index=int(candidate["editor_df"].index[0]))
                        if step["body"]["action"] == "impute_missing_values" and step["body"].get("parameters", {}).get("method", "mode") != "preserve":
                            readiness = column_readiness(candidate, step["body"]["column"], lambda: check(job))
                            if not readiness["ready"]:
                                skipped.append(readiness["message"])
                                continue
                    entry = apply_decision(candidate, step, check=lambda: check(job))
                    entry["automatic_run"] = job["id"]
                    candidate["workflow_steps"][-1]["automatic_run"] = job["id"]
                    entries.append(entry)
                result = {"run_id": job["id"], "operations": entries, "changed_cells": sum(e["changed_cells"] for e in entries if e["action"] != "remove_duplicates"), "removed_rows": sum(e["changed_cells"] for e in entries if e["action"] == "remove_duplicates"), "skipped": skipped}
            elif body.operation in ("plan", "plan_preview"):
                if not body.steps: raise ValueError("Add at least one cleaning action")
                entries = []
                for number, original in enumerate(body.steps):
                    check(job)
                    update(job, stage=f"Cleaning step {number + 1} of {len(body.steps)}", completed_units=number, total_units=len(body.steps))
                    step = original.model_dump()
                    if step["kind"] == "fix":
                        fix = step["body"]
                        if fix["scope"] != "column": raise ValueError("Cleaning plans support whole-column actions only")
                        if candidate["editor_df"].empty: raise ValueError("No rows remain for this action")
                        fix["revision"] = candidate["editor_revision"]
                        fix["row_index"] = int(candidate["editor_df"].index[0])
                    entries.append(apply_decision(candidate, step, check=lambda: check(job)))
                result = {"operations":entries,"changed_cells":sum(item["changed_cells"] for item in entries if item["action"] != "remove_duplicates"),"removed_rows":sum(item["changed_cells"] for item in entries if item["action"] == "remove_duplicates"),"revision":candidate["editor_revision"]}
            elif body.operation == "undo_run":
                ids = [step["id"] for step in candidate["workflow_steps"] if step.get("automatic_run") == body.run_id]
                if not body.run_id or not ids: raise ValueError("This automatic cleaning run has already been undone or is unavailable")
                update(job, stage="Undoing automatic cleaning run and replaying later decisions")
                replay_without(candidate, ids, lambda: check(job))
            elif body.operation == "undo":
                update(job, stage="Replaying remaining decisions")
                replay_without(candidate, body.step_id, lambda: check(job))
            elif body.operation in ("recipe", "recipe_preview"):
                if body.recipe is None: raise ValueError("A recipe is required")
                start = len(candidate.get("complete_changes", []))
                result = apply_recipe(candidate, body.recipe.model_dump(), lambda: check(job), lambda stage, n: update(job, stage=stage, completed_units=n, total_units=len(body.recipe.steps)))
                result["changed_cells"] = len(candidate.get("complete_changes", [])) - start
                result["examples"] = candidate.get("complete_changes", [])[start:start + 10]
            if body.operation == "export":
                update(job, stage="Generating export")
                payload, media, filename = export(candidate, body)
                check(job)
                output = path(job["id"]).with_suffix(".workflow-output")
                with store.lock:
                    store.get(job["file_id"], job["session"])
                    output.write_bytes(payload); os.chmod(output, 0o600)
                    os.utime(output, (job["created"], job["created"]))
                result = {"download": f"/api/workflow-jobs/{job['id']}/download", "filename": filename, "media": media}
            elif body.operation not in ("preview", "recipe_preview", "plan_preview", "quality_review"):
                update(job, stage="Rechecking issues and caching column annotations")
                profile_record(candidate, lambda: check(job))
                if body.operation == "automatic":
                    result["remaining"] = candidate.get("issue_overview", {})
                check(job)
                commit(job, candidate, body.revision)
                result["revision"] = candidate["editor_revision"]
            check(job)
            update(job, status="completed", stage="Completed", result=result, completed_units=job.get("total_units"))
        except Cancelled:
            update(job, status="cancelled", stage="Cancelled; last committed data preserved")
        except Exception as exc:
            update(job, status="failed", error=str(exc) if isinstance(exc, (ValueError, KeyError)) else "Processing failed; last committed data is preserved.")
    @router.post("/files/{file_id}/workflow/init")
    def initialize(file_id: str, request: Request):
        with store.lock:
            record = store.get(file_id, request.state.session)
            existing = bool(record.get("workflow_version"))
            if "editor_df" not in record:
                record.update(editor_df=record["df"].copy(deep=True), editor_profile=record["profile"], editor_revision=0, editor_basic_log=[], editor_changes=[])
                record["preparation_reviewed"] = True
            marker_upgrade = record.get("missing_marker_review_version") != 1
            record["missing_marker_review_version"] = 1
            ensure_workflow(record)
            audit_repaired=record.pop("_audit_repaired",False)
            upgraded = record.get("manual_acceptance_version") != 2 or "issue_overview" not in record or marker_upgrade or record.get("analysis_schema_version") != ANALYSIS_SCHEMA_VERSION
            if upgraded:
                accepted = manual_acceptances(record)
                if marker_upgrade:
                    record.pop("workflow_raw_profile", None)
                    record.pop("workflow_annotations", None)
                    record["_workflow_dirty"] = list(record["editor_df"].columns)
                elif accepted:
                    record["_workflow_dirty"] = list({entry["column"] for entry in accepted})
                profile_record(record)
                record["manual_acceptance_version"] = 2
            if not existing or upgraded or audit_repaired:
                store.save(record)
        return editor_response(record)
    @router.get("/files/{file_id}/workflow/settings")
    def settings(file_id: str, request: Request):
        record = store.get(file_id, request.state.session)
        return {"revision": record["editor_revision"], "protected_columns": sorted({item["column"] for item in manual_acceptances(record)}), "preparation": record.get("preparation_settings") or Preparation().model_dump(), "rules": record.get("column_rules", {}), "cross_column_rules": record.get("cross_column_rules", []), "outlier_rules": record.get("outlier_rules", {}), "ignored": record.get("ignored_findings", []), "legacy_notice": record.get("legacy_history_notice", ""), "recipe": recipe_from(record), "compatibility": record.get("metadata", {})}
    @router.get("/files/{file_id}/workflow/suggested")
    def suggested(file_id: str, request: Request):
        from ..core.suggested_cleaning import suggested_cleaning
        record = store.get(file_id, request.state.session)
        if "editor_df" not in record:
            raise ValueError("Open interactive cleaning first")
        if not record.get("workflow_annotations"):
            profile_record(record)
        return suggested_cleaning(record)
    @router.post("/files/{file_id}/workflow/jobs", status_code=202)
    def start(file_id: str, body: JobInput, request: Request):
        if body.source_job and body.operation != "export":
            raise ValueError("Advanced results can only be used for export")
        record = store.get(file_id, request.state.session)
        if "editor_df" not in record: raise ValueError("Open interactive cleaning first")
        if record["editor_revision"] != body.revision: raise HTTPException(409, "The sheet changed; reload before applying this decision")
        with lock:
            for old in store.root.glob("*.workflow-job"):
                if time.time() - old.stat().st_mtime > 86400:
                    old.with_suffix(".workflow-output").unlink(missing_ok=True); old.unlink(missing_ok=True)
            # Bound retained in-memory jobs and queue; payloads remain local with expiry.
            for key in list(jobs):
                if jobs[key]["status"] not in ("queued", "running") and time.time() - jobs[key]["created"] > 3600: jobs.pop(key)
            active = [j for j in jobs.values() if j["status"] in ("queued", "running")]
            if len(active) >= 8: raise HTTPException(429, "Processing queue is full; retry shortly")
            if any(j["file_id"] == file_id and j["session"] == request.state.session for j in active): raise HTTPException(409, "This file already has an active job. Wait or cancel it first")
            key = str(uuid.uuid4())
            job = {"id": key, "file_id": file_id, "session": request.state.session, "created": time.time(), "status": "queued", "stage": "Queued", "operation": body.operation, "cancel_event": threading.Event()}
            jobs[key] = job; persist(job)
            pool.submit(run, job, record, body)
        return {"job_id": key, "status": "queued"}
    @router.get("/workflow-jobs/{job_id}")
    def status(job_id: str, request: Request):
        job = get_job(job_id, request.state.session)
        return {k: v for k, v in job.items() if k not in ("session", "cancel_event")}
    @router.post("/workflow-jobs/{job_id}/cancel")
    def cancel(job_id: str, request: Request):
        with lock:
            job = get_job(job_id, request.state.session)
            if job["status"] in ("queued", "running") and job.get("cancel_event") and not job.get("committed"):
                job["cancel_event"].set(); update(job, stage="Cancellation requested; finishing the current calculation")
            return {"status": job["status"]}
    @router.get("/workflow-jobs/{job_id}/download")
    def artifact(job_id: str, request: Request):
        job = get_job(job_id, request.state.session)
        if job["status"] != "completed" or job["operation"] != "export": raise HTTPException(409, "Export is not ready")
        content = path(job_id).with_suffix(".workflow-output").read_bytes()
        return StreamingResponse(io.BytesIO(content), media_type=job["result"]["media"], headers={"Content-Disposition": f'attachment; filename="{job["result"]["filename"]}"'})
    @router.get("/files/{file_id}/workflow/changes")
    def changes(file_id: str, request: Request, search: str = "", column: str = "", action: str = "", revision: int | None = None, page: int = Query(1, ge=1)):
        record = store.get(file_id, request.state.session)
        rows = [entry for entry in record.get("complete_changes", []) if (not column or entry["column"] == column) and (not action or entry["action"] == action) and (revision is None or entry["revision"] == revision) and (not search or search.casefold() in json.dumps(entry, ensure_ascii=False).casefold())]
        return {"total": len(rows), "page": page, "rows": rows[(page-1)*50:page*50], "coverage": record.get("legacy_history_notice", ""), "ignored": record.get("ignored_findings", [])}
    @router.get("/files/{file_id}/workflow/recipe")
    def recipe(file_id: str, request: Request):
        return JSONResponse(recipe_from(store.get(file_id, request.state.session)), headers={"Content-Disposition": 'attachment; filename="dataneat-recipe.json"'})
    @router.post("/files/{file_id}/workflow/recipe-check")
    def recipe_check(file_id: str, body: Recipe, request: Request):
        return compatible(store.get(file_id, request.state.session), body.model_dump())
    @router.get("/files/{file_id}/workflow/suggestions")
    def suggestions(file_id: str, request: Request, column: str):
        record = store.get(file_id, request.state.session)
        if column not in record["editor_df"]: raise ValueError("Unknown column")
        counts = {}
        for value in record["editor_df"][column]:
            if isinstance(value, str) and value.strip(): counts[value] = counts.get(value, 0) + 1
        entries = [{"value": v, "count": n} for v, n in sorted(counts.items(), key=lambda pair: -pair[1])]
        return {"groups": suggested_groups(entries), "coverage": "Local spelling suggestions among the 1,000 most frequent values up to 100 characters. Suggestions do not establish equivalence."}
    app.include_router(router)

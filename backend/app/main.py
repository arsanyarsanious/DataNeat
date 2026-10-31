import asyncio
import hashlib
import logging
import io
import os
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .core.cleaner import apply_cleaning_plan, validate_imputation_approval
from .core.cleaning_plan import generate_cleaning_plan
from .core.common import missing, scalar
from .core.date_analyzer import is_valid_date
from .core.file_parser import parse_file, inspect_workbook
from .core.xlsx_presentation import original_colors as original_cell_colors
from .core.interactive import annotate, prepare_original_preview, propose
from .core.profiler import profile_dataframe
from .core.pdf_report import cleaning_pdf
from .core.validator import validate_cleaning
from .models.requests import CleaningRequest, EditorRequest
from .services.limits import BodyLimitMiddleware
from .services.storage import Store
from .services import identity
from pydantic import BaseModel, Field

if os.getenv("CLOUD_STORAGE", "false").lower() == "true":
    from .services.cloud_storage import CloudStore
    store = CloudStore()
else:
    store = Store()
executor = ThreadPoolExecutor(max_workers=int(os.getenv("CLEANING_WORKERS", "2")))
editor_tasks = {}
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
rate = defaultdict(deque)
ALLOWED_ORIGINS = [value.rstrip("/") for value in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if value]
if os.getenv("RENDER_EXTERNAL_URL"):
    ALLOWED_ORIGINS.append(os.environ["RENDER_EXTERNAL_URL"].rstrip("/"))


@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            await run_in_threadpool(store.purge)
            for key, preparation in list(editor_tasks.items()):
                if preparation.done() and not store.path(key[0]).exists():
                    editor_tasks.pop(key, None)
            now = time.monotonic()
            for key in list(rate):
                if not rate[key] or now - rate[key][-1] > 60:
                    rate.pop(key, None)
            await asyncio.sleep(60)

    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    executor.shutdown(wait=True)


app = FastAPI(title="DataNeat API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_UPLOAD + 1024 * 1024)


@app.middleware("http")
async def session_and_limits(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    origin = request.headers.get("origin")
    if (
        request.method in ("POST", "DELETE")
        and origin
        and origin not in ALLOWED_ORIGINS
    ):
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    session = request.cookies.get("dataneat_session")
    try:
        uuid.UUID(session or "")
    except ValueError:
        session = str(uuid.uuid4())
    request.state.session = session
    request.state.user = None
    path = request.url.path
    public_paths = {"/api/health", "/api/auth/config", "/api/auth/session", "/api/auth/logout"}
    key = request.client.host if request.client else "local"
    now = time.monotonic()
    queue = rate[key]
    while queue and now - queue[0] > 60:
        queue.popleft()
    if len(queue) >= 120:
        return JSONResponse(
            {"detail": "Too many requests; retry in a minute"}, status_code=429
        )
    queue.append(now)
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_UPLOAD + 1024 * 1024):
        return JSONResponse({"detail": "Upload limit exceeded"}, status_code=413)
    if identity.configuration()["enabled"] and path not in public_paths:
        try:
            user = await run_in_threadpool(identity.verify, request.cookies.get("dataneat_auth"))
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        request.state.user = user
        # Verified account identity is stable across browser sessions. Anonymous
        # visitors retain their separate, temporary browser workspace.
        request.state.session = hashlib.sha256(("account:" + user["id"]).encode()).hexdigest()
    response = await call_next(request)
    if request.state.user and response.status_code < 400:
        event = (
            "upload" if path == "/api/files/upload" and request.method == "POST" else
            "download" if path.endswith("/download") else
            "editor_start" if path.endswith("/editor/start") and request.method == "POST" else
            "editor_fix" if getattr(request.state, "confirmed_editor_fix", False) else
            "clean" if path.endswith("/clean") and request.method == "POST" else None
        )
        if event:
            try:
                await run_in_threadpool(identity.record, request.state.user, event)
            except Exception:
                logging.getLogger(__name__).warning("Usage counter could not be recorded")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.cookies.get("dataneat_session") != session:
        response.set_cookie(
            "dataneat_session",
            session,
            httponly=True,
            samesite="lax",
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            max_age=86400,
        )
    return response


@app.exception_handler(KeyError)
async def not_found(request, exc):
    return JSONResponse(
        {"detail": "File or job not found in this session"}, status_code=404
    )


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.get("/api/health")
def health():
    from .core.file_parser import MAX_ROWS, MAX_COLUMNS
    return {"status": "ok", "max_upload_mb": MAX_UPLOAD // (1024 * 1024),
            "max_rows": MAX_ROWS, "max_columns": MAX_COLUMNS}


@app.get("/api/auth/config")
def auth_config():
    return identity.configuration()


class AuthSession(BaseModel):
    access_token: str = Field(min_length=1, max_length=8192)


@app.post("/api/auth/session")
def establish_auth(body: AuthSession):
    user = identity.verify(body.access_token)
    response = JSONResponse({"email": user["email"], "admin": identity.administrator(user)})
    response.set_cookie("dataneat_auth", body.access_token, httponly=True, samesite="lax",
                        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=3600)
    # Token refreshes do not count as new sign-ins.
    return response


@app.get("/api/auth/me")
def current_account(request: Request):
    if not request.state.user:
        raise HTTPException(401, "Please sign in to continue.")
    return {"email": request.state.user["email"], "admin": identity.administrator(request.state.user)}


@app.post("/api/auth/sign-in-event")
def sign_in_event(request: Request):
    if not request.state.user:
        raise HTTPException(401, "Please sign in to continue.")
    identity.record(request.state.user, "sign_in")
    return {"recorded": True}


@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.cookies.get("dataneat_auth", "")
    identity.cache.pop(hashlib.sha256(token.encode()).hexdigest(), None)
    response = JSONResponse({"signed_out": True})
    response.delete_cookie("dataneat_auth")
    response.set_cookie("dataneat_session", str(uuid.uuid4()), httponly=True, samesite="lax",
                        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=86400)
    return response


@app.get("/api/admin/usage")
def usage_overview(request: Request):
    if not request.state.user or not identity.administrator(request.state.user):
        raise HTTPException(403, "Administrator access required.")
    return identity.overview()


def preview(df, page=1, page_size=25, logs=None):
    part = df.iloc[(page - 1) * page_size : page * page_size]
    imputed = set()
    for log in logs or []:
        if log["operation"] == "impute_missing_values":
            imputed.update(
                (cell["row_index"], log["column"])
                for cell in log.get("imputed_cells", [])
            )
        elif log["operation"] == "rename_column":
            imputed = {
                (row, log["parameters"]["name"] if col == log["column"] else col)
                for row, col in imputed
            }
    return {
        "is_imputed": [
            [(scalar(row), col) in imputed for col in df.columns] for row in part.index
        ],
        "columns": list(df.columns),
        "rows": [
            [scalar(v) for v in row] for row in part.itertuples(index=False, name=None)
        ],
        "total_rows": len(df),
        "page": page,
        "page_size": page_size,
    }


def file_record(file_id, request):
    with store.lock:
        record = store.get(file_id, request.state.session)
        from .core.imputation_readiness import ANALYSIS_SCHEMA_VERSION
        expected_schema = ANALYSIS_SCHEMA_VERSION if record.get("workflow_version") else 5
        if "editor_df" in record and record.get("analysis_schema_version") != expected_schema:
            if record.get("workflow_version"):
                from .core.workflow import profile_record
                profile_record(record)
            else:
                record["editor_profile"] = profile_dataframe(record["editor_df"])
                for key in ("workflow_annotations", "workflow_raw_profile", "editor_issue_navigation"):
                    record.pop(key, None)
                record["analysis_schema_version"] = 5
            store.save(record)
        return record


@app.post("/api/files/inspect-workbook")
async def inspect_uploaded_workbook(request: Request, file: UploadFile = File(...)):
    # Uses the same authenticated request boundary as uploads, but creates no
    # file record and performs no profiling before an explicit worksheet choice.
    data = bytearray()
    try:
        while chunk := await file.read(1024 * 1024):
            data.extend(chunk)
            if len(data) > MAX_UPLOAD:
                raise HTTPException(413, "Upload limit exceeded")
    finally:
        await file.close()
    if not data:
        raise HTTPException(422, "The file is empty")
    filename = Path((file.filename or "upload").replace("\\", "/")).name
    try:
        return await run_in_threadpool(inspect_workbook, bytes(data), filename)
    except ValueError:
        raise
    except Exception:
        raise HTTPException(422, "Unable to inspect workbook; check its format and contents")


@app.post("/api/files/upload")
async def upload(
    request: Request, file: UploadFile = File(...), sheet: str | None = Form(None)
):
    if len(list(store.root.glob("*.bin"))) >= int(os.getenv("MAX_STORED_FILES", "1000")):
        raise HTTPException(
            503, "Storage capacity reached; delete files or retry later"
        )
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Upload limit exceeded")
    await file.close()
    if not data:
        raise HTTPException(422, "The file is empty")
    filename = Path((file.filename or "upload").replace("\\", "/")).name
    try:
        df, metadata = await run_in_threadpool(parse_file, bytes(data), filename, sheet)
    except ValueError:
        raise
    except Exception:
        raise HTTPException(
            422, "Unable to read spreadsheet; check its format and contents"
        )
    report = await run_in_threadpool(profile_dataframe, df)
    record = {
        "id": str(uuid.uuid4()),
        "session": request.state.session,
        "account_owner": request.state.user["id"] if request.state.user else None,
        "created": time.time(),
        "filename": filename,
        "original_bytes": bytes(data),
        "df": df,
        "metadata": metadata,
        "profile": report,
        "plan": generate_cleaning_plan(df, report),
    }
    store.save(record)
    return {
        "file_id": record["id"],
        "filename": filename,
        "metadata": metadata,
        "preview": preview(df),
        "profile": report,
        "plan": record["plan"],
        "storage": file_storage_status(record),
    }


@app.get("/api/files/{file_id}/workspace")
def restore_workspace(file_id: str, request: Request):
    record = file_record(file_id, request)
    return {"file_id": file_id, "filename": record.get("saved_name") or record["filename"], "metadata": record["metadata"], "preview": preview(record["df"]), "profile": record["profile"], "plan": record["plan"], "storage": file_storage_status(record)}


def file_storage_status(record):
    return {"saved": bool(record.get("saved_to_account")), "saved_name": record.get("saved_name"), "expires_at": store.expires_at(record)}


@app.get("/api/files/{file_id}/preview")
def file_preview(
    file_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    return preview(file_record(file_id, request)["df"], page, page_size)


@app.get("/api/files/{file_id}/invalid-dates")
def invalid_dates(
    file_id: str,
    request: Request,
    column: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    record = file_record(file_id, request)
    if column not in record["df"]:
        raise HTTPException(422, "Unknown column")
    selected = next(
        c for c in record["profile"]["columns"] if c["column_name"] == column
    )
    if "date_analysis" not in selected:
        raise HTTPException(422, "This column is not a detected date column")
    rows, count = [], 0
    start, end = (page - 1) * page_size, page * page_size
    for index, value in record["df"][column].items():
        if not missing(value) and not is_valid_date(value):
            if start <= count < end:
                rows.append(
                    {
                        "row_index": int(index),
                        "spreadsheet_row": int(index) + 2,
                        "value": scalar(value),
                    }
                )
            count += 1
    return {"rows": rows, "total": count, "page": page, "page_size": page_size}


@app.get("/api/files/{file_id}/profile")
def profile(file_id: str, request: Request):
    return file_record(file_id, request)["profile"]


@app.get("/api/files/{file_id}/issues")
def issues(file_id: str, request: Request):
    report = file_record(file_id, request)["profile"]
    return {
        "columns": [i for c in report["columns"] for i in c["issues"]],
        "duplicate_rows": report["duplicate_rows"],
    }


@app.get("/api/files/{file_id}/cleaning-plan")
def plan(file_id: str, request: Request):
    return {"operations": file_record(file_id, request)["plan"]}


@app.post("/api/files/{file_id}/preview-cleaning")
def preview_cleaning(file_id: str, body: CleaningRequest, request: Request, background: bool = False):
    if background:
        return queue_advanced(file_id, body, request, preview_only=True)
    original = file_record(file_id, request)["df"]
    cleaned, logs = apply_reviewed_legacy_plan(
        original, [o.model_dump() for o in body.operations], require_approval=False
    )
    return {
        "before": preview(original),
        "after": preview(cleaned, logs=logs),
        "operations": logs,
        "validation": validate_cleaning(original, cleaned, logs),
    }


def legacy_imputation_readiness(df, column, context=None):
    """Check the staged legacy table without migrating or saving its workflow."""
    from .core.imputation_readiness import ensure_imputation_ready
    staged = dict(context or {})
    staged["editor_df"] = df
    # An earlier legacy normalization or replacement invalidates all findings.
    for key in ("workflow_annotations", "workflow_raw_profile", "editor_issue_navigation"):
        staged.pop(key, None)
    staged["analysis_schema_version"] = 0
    return ensure_imputation_ready(staged, column)


def apply_reviewed_legacy_plan(df, operations, require_approval=True, progress=None):
    """Keep legacy transforms/audits, checking each fill against its actual input."""
    if require_approval:
        validate_imputation_approval(operations)
    if not any(op.get("enabled") and op["operation"] == "impute_missing_values"
               and op.get("parameters", {}).get("method", "preserve") != "preserve"
               for op in operations):
        return apply_cleaning_plan(df, operations, require_approval=require_approval, progress=progress)
    # Match apply_cleaning_plan's dependency order. Each kernel runs once;
    # readiness sees the output of all preceding approved corrections.
    priorities = {"normalize_missing_values": 0, "trim_whitespace": 1,
                  "normalize_numeric": 2, "normalize_boolean": 2,
                  "normalize_dates": 2, "resolve_invalid_dates": 2,
                  "impute_missing_values": 4, "remove_duplicates": 5,
                  "rename_column": 6}
    ordered = sorted(operations, key=lambda op: priorities.get(op["operation"], 3))
    result, logs = df, []
    context = {"editor_changes": []}
    for operation in ordered:
        if progress:
            progress(operation)
        if not operation.get("enabled", False):
            continue
        column, action = operation.get("column"), operation["operation"]
        settings = operation.get("parameters", {})
        if action == "impute_missing_values" and settings.get("method", "preserve") != "preserve":
            legacy_imputation_readiness(result, column, context)
        date_rows = []
        if action == "normalize_dates" and column in result:
            from .core.date_analyzer import parse_formatted_date
            for index, value in result[column].items():
                if missing(value):
                    continue
                try:
                    parse_formatted_date(value, settings.get("interpretation"), settings.get("_source_formats", {}).get(int(index)))
                    date_rows.append(int(index))
                except (ValueError, TypeError, OverflowError):
                    pass
        runtime_operation = operation
        if action == "impute_missing_values":
            from .core.workflow import known_date_formats
            sources = {index: fmt for (name, index), fmt in known_date_formats(context).items() if name == column}
            if sources:
                runtime_operation = {**operation, "parameters": {**settings, "_source_formats": sources}}
        result, current_logs = apply_cleaning_plan(result, [runtime_operation], require_approval=False)
        for entry in current_logs:
            entry["parameters"] = settings
        logs.extend(current_logs)
        if action == "normalize_dates":
            context["editor_changes"].append({"action": action, "column": column,
                                               "parameters": settings, "date_format_rows": date_rows})
    return result, logs


def do_job(job_id, record, operations, preview_only=False):
    try:
        with store.lock:
            if job_id not in store.jobs:
                return
            store.jobs[job_id]["status"] = "running"
        def progress(op):
            with store.lock:
                if job_id not in store.jobs or store.jobs[job_id].get("cancel_requested"):
                    raise InterruptedError("Cancelled; original file preserved")
                store.jobs[job_id]["stage"] = op["operation"].replace("_", " ")
        cleaned, logs = apply_reviewed_legacy_plan(record["df"], operations, require_approval=not preview_only, progress=progress)
        validation = validate_cleaning(record["df"], cleaned, logs)
        with store.lock:
            if job_id in store.jobs:
                if store.jobs[job_id].get("cancel_requested"):
                    raise InterruptedError("Cancelled; original file preserved")
                store.jobs[job_id].update(
                    status="completed",
                    completed_at=time.time(),
                    df=cleaned,
                    operations=logs,
                    validation=validation,
                )
                if preview_only:
                    store.jobs[job_id]["preview_result"] = {"before": preview(record["df"]), "after": preview(cleaned, logs=logs), "operations": logs, "validation": validation}
                store.save_job(store.jobs[job_id])
    except Exception as exc:
        with store.lock:
            if job_id in store.jobs:
                store.jobs[job_id].update(
                    status="cancelled" if isinstance(exc, InterruptedError) else "failed",
                    error=str(exc)
                    if isinstance(exc, ValueError)
                    else "Cleaning failed. Check operation parameters and retry.",
                )
                store.save_job(store.jobs[job_id])


@app.post("/api/files/{file_id}/clean", status_code=202)
def clean(file_id: str, body: CleaningRequest, request: Request):
    return queue_advanced(file_id, body, request)


def queue_advanced(file_id, body, request, preview_only=False):
    record = file_record(file_id, request)
    if not preview_only:
        validate_imputation_approval([o.model_dump() for o in body.operations])
    with store.lock:
        if (
            len(store.jobs) >= 100
            or sum(j["status"] in ("queued", "running") for j in store.jobs.values())
            >= 8
        ):
            raise HTTPException(429, "Cleaning queue is full; retry shortly")
        job_id = str(uuid.uuid4())
        store.jobs[job_id] = {
            "id": job_id,
            "file_id": file_id,
            "session": request.state.session,
            "created": time.time(),
            "status": "queued",
            "filename": record["filename"],
            "kind": "preview" if preview_only else "clean",
            "stage": "Queued",
        }
        store.save_job(store.jobs[job_id])
    executor.submit(do_job, job_id, record, [o.model_dump() for o in body.operations], preview_only)
    return {"job_id": job_id, "status": "queued"}


def job_record(job_id, request, completed=False):
    with store.lock:
        job = store.jobs.get(job_id) or store.load_job(job_id)
        if (
            not job
            or job["session"] != request.state.session
            or time.time() - job["created"] > 86400
        ):
            raise KeyError(job_id)
        if completed and job["status"] != "completed":
            raise HTTPException(409, "Job has not completed")
        store.get(job["file_id"], request.state.session)
        return job.copy()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, request: Request):
    job = job_record(job_id, request)
    return {"job_id": job_id, "status": job["status"], "error": job.get("error"), "stage": job.get("stage")}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_advanced(job_id: str, request: Request):
    job = job_record(job_id, request)
    with store.lock:
        if job_id in store.jobs and job["status"] in ("queued", "running"):
            store.jobs[job_id]["cancel_requested"] = True
    return {"status": job["status"]}


@app.get("/api/jobs/{job_id}/results")
def results(
    job_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    job = job_record(job_id, request, True)
    if job.get("kind") == "preview":
        return job["preview_result"]
    return {
        "preview": preview(job["df"], page, page_size, logs=job["operations"]),
        "validation": job["validation"],
        "operations": job["operations"],
        "filename": job["filename"],
        "cleaned_at": datetime.fromtimestamp(
            job.get("completed_at", job["created"]), timezone.utc
        ).isoformat(),
    }


def safe_export(value):
    if isinstance(value, str) and value.lstrip().startswith(
        ("=", "+", "-", "@", "\t", "\r", "\n")
    ):
        return "'" + value
    return value


@app.get("/api/jobs/{job_id}/download")
def download(
    job_id: str,
    request: Request,
    format: str = Query("csv", pattern="^(csv|xlsx|report|report_json)$"),
):
    job = job_record(job_id, request, True)
    if format == "report":
        pdf = cleaning_pdf(job["filename"], job["operations"], job["validation"]["before"], job["validation"]["after"])
        return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="dataneat-cleaning-report.pdf"'})
    if format == "report_json":
        return JSONResponse(
            {
                "filename": job["filename"],
                "cleaned_at": datetime.fromtimestamp(
                    job.get("completed_at", job["created"]), timezone.utc
                ).isoformat(),
                "operations": job["operations"],
                "validation": job["validation"],
            },
            headers={
                "Content-Disposition": 'attachment; filename="dataneat-report.json"'
            },
        )
    df = job["df"].map(safe_export)
    df.columns = [safe_export(str(c)) for c in df.columns]
    buffer = io.BytesIO()
    if format == "csv":
        buffer.write(df.to_csv(index=False).encode("utf-8-sig"))
        media = "text/csv"
    else:
        df.to_excel(buffer, index=False, engine="openpyxl")
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="dataneat-cleaned.{format}"'
        },
    )


@app.delete("/api/files/{file_id}")
def delete(file_id: str, request: Request, only_temporary: bool = False):
    with store.lock:
        record = store.get(file_id, request.state.session)
        if only_temporary and record.get("saved_to_account"):
            return {"deleted": False, "saved": True}
        store.delete(file_id, request.state.session)
    task = editor_tasks.pop((file_id, request.state.session), None)
    if task is not None:
        task.cancel()
    return {"deleted": True}


def editor_response(record, page=1, page_size=25, affected_only=False, issue_column="", issue_kind="any", original_colors=False):
    df = record["editor_df"]
    report = record["editor_profile"]
    # Older saved profiles must expose new supported date methods immediately,
    # without changing the working data or recomputing full-file annotations.
    for column in report["columns"]:
        if column["detected_type"] in ("date", "datetime") and column.get("total_rows", len(df)) > column.get("missing_count", 0):
            methods = column.get("imputation", {}).get("available_methods")
            if methods is not None:
                for method in ("median", "group_median"):
                    if method not in methods: methods.append(method)
    view = df
    if issue_column and issue_column not in df.columns:
        raise HTTPException(422, "Unknown issue column")
    if affected_only:
        if not record.get("workflow_annotations"):
            from .core.workflow import profile_record
            profile_record(record)
        matching = set()
        for name, cells in record["workflow_annotations"].items():
            if issue_column and name != issue_column: continue
            for index, flags in cells.items():
                if issue_kind == "any" or any(flag["kind"] == issue_kind for flag in flags): matching.add(index)
        view = df.loc[df.index.isin(matching)]
    page = min(page, max(1, (len(view) + page_size - 1) // page_size))
    data = preview(view, page, page_size)
    data["filtered"] = affected_only
    data["dataset_rows"] = len(df)
    data["row_indices"] = [
        int(i) for i in view.iloc[(page - 1) * page_size : page * page_size].index
    ]
    estimates = {}
    changes_by_step = {}
    for change in record.get("complete_changes", []):
        changes_by_step.setdefault(change["step_id"], []).append(change)
    for entry in record.get("editor_changes", []):
        column = entry.get("column")
        if entry.get("action") == "rename_column":
            estimates[entry["parameters"]["name"]] = estimates.pop(column, set())
        elif entry.get("action") == "impute_missing_values" and entry.get("parameters", {}).get("method") != "constant":
            estimates.setdefault(column, set()).update(cell["row_index"] for cell in entry.get("imputation", {}).get("imputed_cells", []))
        elif entry.get("action") in ("replace", "unify_text_values") or entry.get("action") == "impute_missing_values" and entry.get("parameters", {}).get("method") == "constant":
            for cell in changes_by_step.get(entry.get("id"), []):
                estimates.get(cell["column"], set()).discard(cell["row_index"])
    data["is_imputed"] = [[index in estimates.get(column, set()) for column in df.columns] for index in data["row_indices"]]
    if record.get("workflow_version"):
        from .core.workflow import estimated_cells, manual_acceptances
        surviving_estimates = estimated_cells(record)
        # Explicit user constants remain excluded as statistical donors, but the
        # sheet presents them as accepted user values rather than estimates.
        surviving_estimates -= {(entry["column"], entry["row_index"]) for entry in manual_acceptances(record)}
        data["is_imputed"] = [[(column, index) in surviving_estimates for column in df.columns] for index in data["row_indices"]]
    cached = record.get("workflow_annotations")
    if cached:
        indices = list(df.index)
        positions = {int(index): position for position, index in enumerate(indices)}
        data["cell_issues"] = [[cached[c].get(index, []) if isinstance(cached[c], dict) else cached[c][positions[index]][0] for c in df.columns] for index in data["row_indices"]]
    else:
        from .core.workflow import workflow_annotations, manual_acceptances
        data["cell_issues"] = workflow_annotations(df, report, view.iloc[(page - 1) * page_size : page * page_size], ignored=[*record.get("ignored_findings", []), *manual_acceptances(record)])
    return {
        "preview": data,
        "original_colors": original_cell_colors(record, data, original_colors),
        "profile": report,
        "revision": record["editor_revision"],
        "basic_log": record["editor_basic_log"],
        "changes": record.get("editor_changes", []),
        "workflow_version": record.get("workflow_version"),
        "legacy_notice": record.get("legacy_history_notice", ""),
        "overview": record.get("issue_overview") or {
            "columns":sum(bool(cells) for cells in (cached or {}).values()),
            "cells":sum(len(cells) for cells in (cached or {}).values()),
            "types":len({item["kind"] for cells in (cached or {}).values() if isinstance(cells, dict) for flags in cells.values() for item in flags}),
        },
        "automatic_runs": list(dict.fromkeys(step["automatic_run"] for step in record.get("workflow_steps", []) if step.get("automatic_run"))),
    }


@app.post("/api/files/{file_id}/editor/start")
def start_editor(file_id: str, request: Request, background: bool = False):
    with store.lock:
        record = file_record(file_id, request)
        if background and "editor_df" not in record:
            key = (file_id, request.state.session)
            task = editor_tasks.get(key)
            if task is None or task.done():
                editor_tasks[key] = executor.submit(
                    prepare_editor, file_id, request.state.session, record["df"]
                )
            return JSONResponse({"status": "processing"}, status_code=202)
        if "editor_df" not in record:
            cleaned, logs = prepare_original_preview(record["df"])
            record.update(
                editor_df=cleaned,
                editor_profile=profile_dataframe(cleaned),
                editor_revision=0,
                editor_basic_log=logs,
                editor_changes=[],
            )
            store.save(record)
        return editor_response(record)


def prepare_editor(file_id, session, original):
    # Do expensive work outside the storage lock so status requests remain fast.
    cleaned, logs = prepare_original_preview(original)
    report = profile_dataframe(cleaned)
    with store.lock:
        try:
            record = store.get(file_id, session)
        except KeyError:
            return  # An upload deleted during preparation must stay deleted.
        if "editor_df" not in record:
            record.update(
                editor_df=cleaned,
                editor_profile=report,
                editor_revision=0,
                editor_basic_log=logs,
                editor_changes=[],
            )
            store.save(record)


@app.get("/api/files/{file_id}/editor/status")
def editor_status(file_id: str, request: Request):
    record = file_record(file_id, request)
    key = (file_id, request.state.session)
    if "editor_df" in record:
        editor_tasks.pop(key, None)
        return {"status": "ready"}
    task = editor_tasks.get(key)
    if task is None:
        raise HTTPException(409, "Preparation was interrupted. Reopen the interactive spreadsheet to retry.")
    if task.done():
        raise HTTPException(500, "The interactive spreadsheet could not be prepared. Reopen it to retry.")
    return {"status": "processing"}


@app.get("/api/files/{file_id}/editor")
def get_editor(
    file_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    affected_only: bool = False,
    issue_column: str = "",
    issue_kind: str = "any",
    original_colors: bool = False,
):
    record = file_record(file_id, request)
    if "editor_df" not in record:
        raise HTTPException(409, "Start interactive cleaning first")
    return editor_response(record, page, page_size, affected_only, issue_column, issue_kind, original_colors)


@app.get("/api/files/{file_id}/editor/search")
def search_editor(file_id: str, request: Request, q: str = Query(min_length=1, max_length=200), column: str = "", after: int = Query(-1, ge=-1)):
    record = file_record(file_id, request)
    if "editor_df" not in record: raise HTTPException(409, "Start interactive cleaning first")
    from .core.sheet_navigation import find_value
    try: return find_value(record["editor_df"], q, column, after)
    except ValueError as exc: raise HTTPException(422, str(exc))


@app.get("/api/files/{file_id}/editor/compare")
def compare_editor(file_id: str, request: Request, page: int = Query(1, ge=1)):
    record = file_record(file_id, request)
    if "editor_df" not in record: raise HTTPException(409, "Start interactive cleaning first")
    from .core.sheet_navigation import compare_original
    return compare_original(record, page)


@app.get("/api/files/{file_id}/editor/scope-counts")
def editor_scope_counts(file_id: str, request: Request, column: str, row_index: int, kind: str = ""):
    record = file_record(file_id, request)
    df = record.get("editor_df")
    if df is None or column not in df.columns or row_index not in df.index:
        raise HTTPException(422, "Choose an existing cell")
    from .core.common import scalar
    value = scalar(df.at[row_index, column])
    if not record.get("workflow_annotations"):
        from .core.workflow import profile_record
        profile_record(record)
    cells = record.get("workflow_annotations", {}).get(column, {})
    return {"cell":1, "matching":sum(type(scalar(v)) is type(value) and scalar(v) == value for v in df[column]), "issue":sum(any(item["kind"] == kind for item in flags) for flags in cells.values()), "column":len(df)}


@app.get("/api/files/{file_id}/editor/next-issue")
def next_editor_issue(file_id: str, request: Request, column: str, kind: str = "any", after: int = -1, page_size: int = Query(25, ge=1, le=100), distinct_types: bool = False, seen_kinds: str = ""):
    record = file_record(file_id, request)
    if "editor_df" not in record:
        raise HTTPException(409, "Start interactive cleaning first")
    df = record["editor_df"]
    if column not in df.columns:
        raise HTTPException(422, "Unknown column")
    cache = record.get("editor_issue_navigation", {})
    if cache.get("revision") != record["editor_revision"]:
        cache = {"revision": record["editor_revision"], "columns": {}}
    if column not in cache["columns"]:
        from .core.workflow import workflow_annotations
        cached_cells = record.get("workflow_annotations", {}).get(column)
        cells = [[cached_cells.get(int(index), [])] for index in df.index] if isinstance(cached_cells, dict) else cached_cells if cached_cells is not None else workflow_annotations(df, record["editor_profile"], df[[column]], columns=[column], ignored=record.get("ignored_findings"))
        cache["columns"][column] = [{"position": position, "row_index": int(index), "kinds": [issue["kind"] for issue in row[0]]} for position, (index, row) in enumerate(zip(df.index, cells)) if row[0]]
        if cached_cells is None:
            with store.lock:
                current = file_record(file_id, request)
                if current["editor_revision"] == record["editor_revision"]:
                    current["editor_issue_navigation"] = cache
                    store.save(current)
    matches = [entry for entry in cache["columns"][column] if kind == "any" or kind in entry["kinds"]]
    if not matches:
        return {"total": 0, "available_kinds": [], "target": None}
    types = {issue_kind for entry in matches for issue_kind in entry["kinds"] if kind == "any" or issue_kind == kind}
    if distinct_types:
        seen = set(seen_kinds.split(",")) - {""}
        candidates = [entry for entry in matches if any(issue_kind in types - seen for issue_kind in entry["kinds"])]
        if not candidates:
            return {"total": len(matches), "total_types": len(types), "available_kinds": sorted(types), "all_types_seen": True, "target": None}
        target = next((entry for entry in candidates if entry["position"] > after), candidates[0])
        new_kinds = [issue_kind for issue_kind in target["kinds"] if issue_kind in types - seen]
        return {"total": len(matches), "total_types": len(types), "available_kinds": sorted(types), "new_kinds": new_kinds, "target": {**target, "page": target["position"] // page_size + 1}}
    target = next((entry for entry in matches if entry["position"] > after), matches[0])
    return {"total": len(matches), "ordinal": matches.index(target) + 1, "target": {**target, "page": target["position"] // page_size + 1}}

@app.get("/api/files/{file_id}/editor/text-values")
def editor_text_values(file_id: str, request: Request, column: str):
    with store.lock:
        record = file_record(file_id, request)
        if "editor_df" not in record:
            raise HTTPException(409, "Start interactive cleaning first")
        df = record["editor_df"]
        if column not in df.columns:
            raise HTTPException(422, "Unknown column")
        counts = {}
        for index, value in df[column].items():
            if isinstance(value, str) and value.strip():
                item = counts.setdefault(value, {"value": value, "count": 0, "row_index": int(index)})
                item["count"] += 1
        return {"revision": record["editor_revision"], "values": sorted(counts.values(), key=lambda item: (-item["count"], item["value"]))}


@app.post("/api/files/{file_id}/editor/fix")
def editor_fix(file_id: str, body: EditorRequest, request: Request):
    snapshot = file_record(file_id, request)
    if snapshot.get("workflow_version"):
        if snapshot["editor_revision"] != body.revision:
            raise HTTPException(409, "The sheet changed. Reload it and preview the fix again.")
        if body.confirmed:
            raise HTTPException(409, "Use the background workflow to apply this change")
        from .core.workflow import apply_decision
        # Store.get returns a fresh deserialized snapshot; preview never saves it.
        detail = apply_decision(snapshot, {"kind": "fix", "body": body.model_dump()})
        return {"proposal": {**{k: detail[k] for k in ("changed_cells", "examples", "warnings")}, "interpreted_dates": detail.get("interpreted_dates", 0)}}
    with store.lock:
        record = file_record(file_id, request)
        if "editor_df" not in record:
            raise HTTPException(409, "Start interactive cleaning first")
        if record["editor_revision"] != body.revision:
            raise HTTPException(
                409, "The sheet changed. Reload it and preview the fix again."
            )
        if body.action == "impute_missing_values" and body.parameters.get("method", "mode") != "preserve":
            legacy_imputation_readiness(record["editor_df"], body.column, record)
        result, detail = propose(record["editor_df"], body)
        if body.action == "replace":
            from .core.imputation_readiness import actual_empty
            if any(index in result.index and actual_empty(value) and not actual_empty(result.at[index, body.column])
                   for index, value in record["editor_df"][body.column].items()):
                legacy_imputation_readiness(record["editor_df"], body.column, record)
        if not body.confirmed:
            return {"proposal": detail, "revision": record["editor_revision"]}
        request.state.confirmed_editor_fix = True
        if "editor_replay_base" not in record:
            record["editor_replay_base"] = record["editor_df"].copy(deep=True)
            record["editor_replay"] = []
        change_id = str(uuid.uuid4())
        record["editor_replay"].append({"id": change_id, "body": body.model_dump()})
        record.update(
            editor_df=result,
            editor_profile=profile_dataframe(result),
            editor_revision=record["editor_revision"] + 1,
        )
        record["editor_changes"].append(
            {
                "id": change_id,
                "action": body.action,
                "column": body.column,
                "scope": body.scope,
                "row_index": body.row_index,
                "parameters": body.parameters,
                **detail,
            }
        )
        store.save(record)
        return {"proposal": detail, "revision": record["editor_revision"]}


@app.post("/api/files/{file_id}/editor/undo/{change_id}")
def editor_undo(file_id: str, change_id: str, request: Request, revision: int = Query(ge=0)):
    with store.lock:
        record = file_record(file_id, request)
        if record.get("workflow_version"):
            raise HTTPException(409, "Use the enhanced background undo workflow. Earlier baseline work remains preserved.")
        if record.get("editor_revision") != revision:
            raise HTTPException(409, "The sheet changed. Reload before undoing.")
        steps = record.get("editor_replay", [])
        if not any(step["id"] == change_id for step in steps):
            raise HTTPException(409, "This step predates undo support or has already been removed.")
        remaining = [step for step in steps if step["id"] != change_id]
        result = record["editor_replay_base"].copy(deep=True)
        replay_ids = {step["id"] for step in steps}
        changes = [change for change in record["editor_changes"] if change.get("id") not in replay_ids]
        try:
            for step in remaining:
                body = EditorRequest(**step["body"])
                result, detail = propose(result, body)
                changes.append({"id": step["id"], "action": body.action, "column": body.column, "scope": body.scope, "row_index": body.row_index, "parameters": body.parameters, **detail})
        except (ValueError, KeyError) as exc:
            raise HTTPException(409, "A later step depends on this change. Undo the dependent later step first.") from exc
        record.update(editor_df=result, editor_profile=profile_dataframe(result), editor_revision=revision + 1, editor_replay=remaining, editor_changes=changes)
        store.save(record)
        return {"revision": record["editor_revision"]}


@app.get("/api/files/{file_id}/editor/download")
def editor_download(
    file_id: str,
    request: Request,
    format: str = Query("xlsx", pattern="^(csv|xlsx|report|report_json)$"),
):
    record = file_record(file_id, request)
    if "editor_df" not in record:
        raise HTTPException(409, "Start interactive cleaning first")
    if format == "report":
        preparation = ["Recognized missing-value markers were converted to blank cells in the working copy.", "Leading/trailing whitespace and repeated whitespace were normalized. Other changes required Apply change."]
        if record.get("editor_basic_log"):
            preparation = [f"{log['column']}: {log['operation'].replace('_', ' ')}; {log['modified_values']} values changed." for log in record["editor_basic_log"]]
        pdf = cleaning_pdf(record["filename"], record["editor_changes"], record["profile"], record["editor_profile"], preparation, record["editor_revision"])
        return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="dataneat-interactive-report.pdf"'})
    if format == "report_json":
        return JSONResponse(
            {
                "basic_cleanup": record["editor_basic_log"],
                "confirmed_changes": record["editor_changes"],
                "revision": record["editor_revision"],
                "remaining_profile": record["editor_profile"],
            },
            headers={
                "Content-Disposition": 'attachment; filename="dataneat-interactive-report.json"'
            },
        )
    df = record["editor_df"].map(safe_export)
    df.columns = [safe_export(str(c)) for c in df.columns]
    buffer = io.BytesIO()
    if format == "csv":
        buffer.write(df.to_csv(index=False).encode("utf-8-sig"))
    else:
        df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv"
        if format == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="dataneat-interactive.{format}"'
        },
    )

# Enhanced workflows are owner-scoped and use the existing editor/export formats.
from .services.workflow_jobs import install_workflows
install_workflows(app, store, editor_response, safe_export)
from .services.account_files import install_account_files
install_account_files(app, store)
from .services.static_site import install_static_site
install_static_site(app)

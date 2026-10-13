import asyncio
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
from .core.file_parser import parse_file
from .core.interactive import annotate, basic_cleanup, propose
from .core.profiler import profile_dataframe
from .core.validator import validate_cleaning
from .models.requests import CleaningRequest, EditorRequest
from .services.limits import BodyLimitMiddleware
from .services.storage import Store

store = Store()
executor = ThreadPoolExecutor(max_workers=2)
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
rate = defaultdict(deque)


@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            store.purge()
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
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_UPLOAD + 1024 * 1024)


@app.middleware("http")
async def session_and_limits(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method in ("POST", "DELETE")
        and origin
        and origin not in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    ):
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    session = request.cookies.get("dataneat_session")
    try:
        uuid.UUID(session or "")
    except ValueError:
        session = str(uuid.uuid4())
    request.state.session = session
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
    response = await call_next(request)
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
    return {"status": "ok", "max_upload_mb": MAX_UPLOAD // (1024 * 1024)}


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
    return store.get(file_id, request.state.session)


@app.post("/api/files/upload")
async def upload(
    request: Request, file: UploadFile = File(...), sheet: str | None = Form(None)
):
    if len(list(store.root.glob("*.bin"))) >= 100:
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
    }


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
def preview_cleaning(file_id: str, body: CleaningRequest, request: Request):
    original = file_record(file_id, request)["df"]
    cleaned, logs = apply_cleaning_plan(
        original, [o.model_dump() for o in body.operations], require_approval=False
    )
    return {
        "before": preview(original),
        "after": preview(cleaned, logs=logs),
        "operations": logs,
        "validation": validate_cleaning(original, cleaned, logs),
    }


def do_job(job_id, record, operations):
    try:
        with store.lock:
            if job_id not in store.jobs:
                return
            store.jobs[job_id]["status"] = "running"
        cleaned, logs = apply_cleaning_plan(record["df"], operations)
        validation = validate_cleaning(record["df"], cleaned, logs)
        with store.lock:
            if job_id in store.jobs:
                store.jobs[job_id].update(
                    status="completed",
                    completed_at=time.time(),
                    df=cleaned,
                    operations=logs,
                    validation=validation,
                )
    except Exception as exc:
        with store.lock:
            if job_id in store.jobs:
                store.jobs[job_id].update(
                    status="failed",
                    error=str(exc)
                    if isinstance(exc, ValueError)
                    else "Cleaning failed. Check operation parameters and retry.",
                )


@app.post("/api/files/{file_id}/clean", status_code=202)
def clean(file_id: str, body: CleaningRequest, request: Request):
    record = file_record(file_id, request)
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
        }
    executor.submit(do_job, job_id, record, [o.model_dump() for o in body.operations])
    return {"job_id": job_id, "status": "queued"}


def job_record(job_id, request, completed=False):
    with store.lock:
        job = store.jobs.get(job_id)
        if (
            not job
            or job["session"] != request.state.session
            or time.time() - job["created"] > 86400
        ):
            raise KeyError(job_id)
        if completed and job["status"] != "completed":
            raise HTTPException(409, "Job has not completed")
        return job.copy()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, request: Request):
    job = job_record(job_id, request)
    return {"job_id": job_id, "status": job["status"], "error": job.get("error")}


@app.get("/api/jobs/{job_id}/results")
def results(
    job_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    job = job_record(job_id, request, True)
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
    format: str = Query("csv", pattern="^(csv|xlsx|report)$"),
):
    job = job_record(job_id, request, True)
    if format == "report":
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
def delete(file_id: str, request: Request):
    store.delete(file_id, request.state.session)
    return {"deleted": True}


def editor_response(record, page=1, page_size=25):
    df = record["editor_df"]
    report = record["editor_profile"]
    page = min(page, max(1, (len(df) + page_size - 1) // page_size))
    data = preview(df, page, page_size)
    data["row_indices"] = [
        int(i) for i in df.iloc[(page - 1) * page_size : page * page_size].index
    ]
    data["cell_issues"] = annotate(
        df, report, df.iloc[(page - 1) * page_size : page * page_size]
    )
    return {
        "preview": data,
        "profile": report,
        "revision": record["editor_revision"],
        "basic_log": record["editor_basic_log"],
        "changes": record.get("editor_changes", []),
    }


@app.post("/api/files/{file_id}/editor/start")
def start_editor(file_id: str, request: Request):
    with store.lock:
        record = file_record(file_id, request)
        if "editor_df" not in record:
            cleaned, logs = basic_cleanup(record["df"])
            record.update(
                editor_df=cleaned,
                editor_profile=profile_dataframe(cleaned),
                editor_revision=0,
                editor_basic_log=logs,
                editor_changes=[],
            )
            store.save(record)
        return editor_response(record)


@app.get("/api/files/{file_id}/editor")
def get_editor(
    file_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    record = file_record(file_id, request)
    if "editor_df" not in record:
        raise HTTPException(409, "Start interactive cleaning first")
    return editor_response(record, page, page_size)


@app.post("/api/files/{file_id}/editor/fix")
def editor_fix(file_id: str, body: EditorRequest, request: Request):
    with store.lock:
        record = file_record(file_id, request)
        if "editor_df" not in record:
            raise HTTPException(409, "Start interactive cleaning first")
        if record["editor_revision"] != body.revision:
            raise HTTPException(
                409, "The sheet changed. Reload it and preview the fix again."
            )
        result, detail = propose(record["editor_df"], body)
        if not body.confirmed:
            return {"proposal": detail, "revision": record["editor_revision"]}
        record.update(
            editor_df=result,
            editor_profile=profile_dataframe(result),
            editor_revision=record["editor_revision"] + 1,
        )
        record["editor_changes"].append(
            {
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


@app.get("/api/files/{file_id}/editor/download")
def editor_download(
    file_id: str,
    request: Request,
    format: str = Query("xlsx", pattern="^(csv|xlsx|report)$"),
):
    record = file_record(file_id, request)
    if "editor_df" not in record:
        raise HTTPException(409, "Start interactive cleaning first")
    if format == "report":
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

"""Revocable, read-only review links for one current working copy.

A share token is an HMAC-signed, expiring bearer secret. It grants read-only
access to a review summary and the PDF report of one file. It never authorizes
edits, exports or deletion. The link stops working when it expires, when the
owner revokes it (the file's share epoch changes), or when the stored file
expires or is deleted.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..core.common import scalar
from ..core.pdf_report import cleaning_pdf

DEFAULT_TTL_HOURS = 168
MAX_TTL_HOURS = 720
KEY_FILE = ".share-key"
INVALID = "This review link is invalid, expired or was revoked."


def _key(store):
    configured = os.getenv("SHARE_SIGNING_KEY", "") or os.getenv("STORAGE_SIGNING_KEY", "")
    if len(configured) >= 32:
        return configured.encode()
    # Local development without cloud storage: keep one private key on disk.
    path = Path(store.root) / KEY_FILE
    try:
        stored = path.read_bytes()
    except OSError:
        stored = secrets.token_bytes(32)
        temporary = path.with_suffix(".share-key-tmp")
        temporary.write_bytes(stored)
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(path)
    if len(stored) < 32:
        raise RuntimeError("The share signing key must contain at least 32 bytes")
    return stored


def _sign(payload, store):
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=")
    signature = hmac.new(_key(store), raw, hashlib.sha256).digest()
    return (raw + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


def _verify(token, store):
    try:
        raw, encoded = token.encode("ascii").split(b".", 1)
        signature = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))
        expected = hmac.new(_key(store), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4)))
        if payload.get("v") != 1:
            raise ValueError("version")
        file_id, epoch, expires = payload["f"], payload["e"], int(payload["x"])
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise HTTPException(404, INVALID) from None
    if not isinstance(file_id, str) or not isinstance(epoch, str) or not epoch:
        raise HTTPException(404, INVALID)
    if expires <= time.time():
        raise HTTPException(404, INVALID)
    return file_id, epoch, expires


def install_sharing(app, store):
    router = APIRouter(prefix="/api")

    def owned(file_id, request):
        return store.get(file_id, request.state.session)

    def review(record):
        frame = record.get("editor_df")
        if frame is None:
            frame = record.get("df")
        if frame is None:
            raise HTTPException(404, INVALID)
        columns = [str(column) for column in frame.columns]
        head = frame.head(25)
        changes = [
            {
                "action": entry.get("action", ""),
                "column": entry.get("column", ""),
                "changed_cells": entry.get("changed_cells", 0),
            }
            for entry in record.get("editor_changes", [])
        ]
        return {
            "filename": record.get("saved_name") or record.get("filename", "Spreadsheet"),
            "revision": int(record.get("editor_revision", 0)),
            "rows": int(len(frame)),
            "columns": len(columns),
            "changes": changes,
            "issues": record.get("issue_overview") or {},
            "preview": {
                "columns": columns,
                "rows": [
                    [scalar(value) for value in row]
                    for row in head.itertuples(index=False, name=None)
                ],
                "total_rows": int(len(frame)),
            },
            "read_only": True,
        }

    def shared(token):
        file_id, epoch, expires = _verify(token, store)
        try:
            record = store.get_shared(file_id)
        except KeyError:
            raise HTTPException(404, INVALID) from None
        if not hmac.compare_digest(str(record.get("share_epoch") or ""), epoch):
            raise HTTPException(404, INVALID)
        return record, expires

    @router.get("/files/{file_id}/share")
    def share_status(file_id: str, request: Request):
        record = owned(file_id, request)
        epoch = record.get("share_epoch")
        if not isinstance(epoch, str) or not epoch:
            return {"active": False}
        created = float(record.get("share_created", 0))
        hours = int(record.get("share_ttl_hours", DEFAULT_TTL_HOURS))
        return {
            "active": True,
            "created_at": created,
            "expires_at": created + hours * 3600,
            "ttl_hours": hours,
        }

    @router.post("/files/{file_id}/share")
    def create_share(
        file_id: str,
        request: Request,
        ttl_hours: int = Query(DEFAULT_TTL_HOURS, ge=1, le=MAX_TTL_HOURS),
    ):
        with store.lock:
            record = owned(file_id, request)
            now = time.time()
            epoch = record.get("share_epoch")
            if not isinstance(epoch, str) or not epoch:
                epoch = secrets.token_hex(8)
            record["share_epoch"] = epoch
            record["share_created"] = now
            record["share_ttl_hours"] = ttl_hours
            store.save(record)
        token = _sign(
            {"v": 1, "f": file_id, "e": epoch, "x": int(now) + ttl_hours * 3600},
            store,
        )
        return {
            "token": token,
            "expires_at": int(now) + ttl_hours * 3600,
            "ttl_hours": ttl_hours,
        }

    @router.delete("/files/{file_id}/share")
    def revoke_share(file_id: str, request: Request):
        with store.lock:
            record = owned(file_id, request)
            record["share_epoch"] = secrets.token_hex(8)
            record["share_created"] = 0
            store.save(record)
        return {"revoked": True}

    @router.get("/share/{token}")
    def share_view(token: str):
        record, expires = shared(token)
        return {**review(record), "expires_at": expires, "file_id": record.get("id", "")}

    @router.get("/share/{token}/report")
    def share_report(token: str):
        record, _ = shared(token)
        before = record.get("profile") or {}
        after = record.get("editor_profile") or before
        preparation = [
            "Shared read-only review. The original upload is preserved separately.",
            "This report explains the recorded cleaning steps; it is not a copy of the original workbook.",
        ]
        pdf = cleaning_pdf(
            record.get("filename", "Spreadsheet"),
            record.get("editor_changes", []),
            before,
            after,
            preparation,
            record.get("editor_revision"),
        )
        return StreamingResponse(
            pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="dataneat-review-report.pdf"',
                "Cache-Control": "no-store",
            },
        )

    app.include_router(router)

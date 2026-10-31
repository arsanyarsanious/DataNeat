"""Verified-account file library with explicit, durable retention choices."""
import hashlib
import os
import pickle
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator


class FileName(BaseModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def readable_name(cls, value):
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError("Enter a file name without control characters.")
        return value


def install_account_files(app, store):
    router = APIRouter(prefix="/api/account/files", tags=["Account files"])

    def account(request):
        user = getattr(request.state, "user", None)
        if not user or not user.get("id"):
            raise HTTPException(401, "Sign in to save files to your account.")
        session = hashlib.sha256(("account:" + user["id"]).encode()).hexdigest()
        if request.state.session != session:
            raise HTTPException(401, "Please sign in again to access your account files.")
        return user["id"], session

    def owned(file_id, request):
        owner, session = account(request)
        record = store.get(file_id, session)
        if record.get("account_owner") not in (None, owner):
            raise KeyError(file_id)
        return record, owner, session

    def public(info):
        return {"saved": bool(info.get("saved_to_account")), **{key: info.get(key) for key in (
            "file_id", "filename", "saved_name", "saved_at", "updated_at",
            "rows", "columns", "revision", "saved_to_account", "expires_at", "size_bytes",
        )}}

    def metadata(record):
        info = store._retention(record["id"])
        if info is None:
            info = store._write_retention(record, store.path(record["id"]).stat().st_size)
        return public(info)

    def limits():
        return max(1, int(os.getenv("MAX_ACCOUNT_FILES", "100"))), max(1, int(os.getenv("MAX_ACCOUNT_STORAGE_MB", "1024"))) * 1024 * 1024

    @router.get("")
    def list_files(request: Request):
        owner, session = account(request)
        files = store.account_files(owner, session)
        max_files, max_bytes = limits()
        return {"files": [public(info) for info in files], "storage": {
            "saved_files": len(files), "saved_bytes": sum(info.get("size_bytes", 0) for info in files),
            "max_saved_files": max_files, "max_saved_bytes": max_bytes,
        }}

    @router.get("/{file_id}/status")
    @router.get("/{file_id}")
    def status(file_id: str, request: Request):
        with store.lock:
            record, _, _ = owned(file_id, request)
            return metadata(record)

    @router.post("/{file_id}/save")
    def save(file_id: str, request: Request, body: FileName | None = None):
        with store.lock:
            record, owner, session = owned(file_id, request)
            files = store.account_files(owner, session)
            max_files, max_bytes = limits()
            if not record.get("saved_to_account") and len(files) >= max_files:
                raise HTTPException(409, f"Your account can save up to {max_files} files. Delete a saved file before saving another.")
            record.update(account_owner=owner, saved_to_account=True,
                          saved_at=record.get("saved_at") or time.time(),
                          saved_name=body.name if body else record.get("saved_name") or record["filename"])
            record.pop("expires_at", None)
            projected = sum(info.get("size_bytes", 0) for info in files if info["file_id"] != file_id) + len(pickle.dumps(record))
            if projected > max_bytes:
                raise HTTPException(409, "Your account storage is full. Delete a saved file before saving this one.")
            store.save(record, retention_update=True)
            return metadata(record)

    @router.post("/{file_id}/temporary")
    def temporary(file_id: str, request: Request):
        with store.lock:
            record, _, _ = owned(file_id, request)
            # Choosing temporary starts a fresh, visible 24-hour retention window.
            record.update(saved_to_account=False, expires_at=time.time() + 86400)
            store.save(record, retention_update=True)
            return metadata(record)

    @router.post("/{file_id}/rename")
    def rename(file_id: str, request: Request, body: FileName):
        with store.lock:
            record, _, _ = owned(file_id, request)
            if not record.get("saved_to_account"):
                raise HTTPException(409, "Save this file to your account before renaming it.")
            record["saved_name"] = body.name
            store.save(record, retention_update=True)
            return metadata(record)

    @router.delete("/{file_id}")
    def delete(file_id: str, request: Request):
        with store.lock:
            record, _, session = owned(file_id, request)
            store.delete(record["id"], session)
            return {"deleted": True, "file_id": file_id}

    app.include_router(router)

"""Single-instance cloud store: atomic remote commits, local read-through cache.

Only the backend service credential can access snapshots. Authenticate the
compressed bytes before unpickling; uploaded spreadsheet bytes are never pickles.
"""
import base64
import hashlib
import hmac
import os
import pickle
import time
import uuid
import zlib

import httpx
from fastapi import HTTPException
from .storage import Store

MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


class SupabaseSnapshots:
    def __init__(self):
        self.url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
        self.key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self.signing_key = os.environ["STORAGE_SIGNING_KEY"].encode()
        if len(self.signing_key) < 32:
            raise RuntimeError("STORAGE_SIGNING_KEY must contain at least 32 characters")
        self.headers = {"apikey": self.key, "Authorization": "Bearer " + self.key}

    def request(self, method, path, **kwargs):
        try:
            result = httpx.request(method, self.url + path, headers=self.headers,
                                   timeout=40, follow_redirects=False, **kwargs)
        except httpx.HTTPError:
            raise HTTPException(503, "Cloud storage is unavailable. Your change was not confirmed; please retry.") from None
        if result.status_code >= 400:
            # Database errors can include internal details; return only known codes.
            if "DATANEAT_QUOTA" in result.text:
                raise HTTPException(409, "Free beta storage is full. Download and delete files you no longer need, then retry.")
            if "DATANEAT_OWNER" in result.text:
                raise HTTPException(409, "This file cannot be replaced. Please upload a new copy.")
            raise HTTPException(503, "Cloud storage could not complete this action. Please retry.")
        return result.json() if result.content else None

    def encode(self, record):
        raw = pickle.dumps(record, protocol=5)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise HTTPException(413, "This file's cleaning history exceeds the free beta workspace limit. Export your results and start a new file.")
        compressed = zlib.compress(raw)
        signature = hmac.new(self.signing_key, compressed, hashlib.sha256).hexdigest()
        return signature + "." + base64.b64encode(compressed).decode()

    def decode(self, payload, key, session):
        try:
            signature, encoded = payload.split(".", 1)
            compressed = base64.b64decode(encoded, validate=True)
            expected = hmac.new(self.signing_key, compressed, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            decompressor = zlib.decompressobj()
            raw = decompressor.decompress(compressed, MAX_SNAPSHOT_BYTES + 1)
            if len(raw) > MAX_SNAPSHOT_BYTES or not decompressor.eof or decompressor.unused_data:
                raise ValueError("size")
            record = pickle.loads(raw)
            if record["id"] != key or record["session"] != session:
                raise ValueError("identity")
            return record
        except Exception:
            raise HTTPException(503, "This saved file could not be verified. Please contact support; the stored copy has not been changed.") from None

    def write(self, record, info):
        uuid.UUID(record["account_owner"])
        self.request("POST", "rpc/dataneat_commit_file", json={
            "p_id": record["id"], "p_owner": record["account_owner"],
            "p_session": record["session"], "p_metadata": info,
            "p_payload": self.encode(record), "p_expires": Store.expires_at(record),
        })

    def read(self, key, session):
        rows = self.request("GET", "dataneat_files", params={
            "id": "eq." + key, "session": "eq." + session, "select": "payload", "limit": "1",
        })
        if not rows:
            raise KeyError(key)
        return self.decode(rows[0]["payload"], key, session)

    def list(self, owner, session):
        rows = self.request("GET", "dataneat_files", params={
            "owner": "eq." + owner, "session": "eq." + session,
            "metadata->>saved_to_account": "eq.true", "select": "metadata",
            "order": "updated_at.desc", "limit": "100",
        })
        return [row["metadata"] for row in rows]

    def delete(self, key, session):
        self.request("DELETE", "dataneat_files", params={"id": "eq." + key, "session": "eq." + session})

    def purge(self):
        self.request("DELETE", "dataneat_files", params={"expires_at": "lt." + str(time.time())})


class CloudStore(Store):
    def __init__(self, remote=None):
        super().__init__()
        self.remote = remote if remote is not None else SupabaseSnapshots()
        self.last_cloud_purge = 0

    def save(self, record, *, retention_update=False):
        with self.lock:
            if self.path(record["id"]).exists() and not retention_update:
                self._apply_retention(record, self._retention(record["id"]))
            record["updated_at"] = time.time()
            info = self.metadata(record, len(pickle.dumps(record)))
            # A failed remote commit must never be reported as a successful save.
            self.remote.write(record, info)
            super().save(record, retention_update=True)

    def get(self, key, session):
        with self.lock:
            path = self.path(key)
            if not path.exists():
                record = self.remote.read(key, session)
                expires = self.expires_at(record)
                if record["session"] != session or (expires is not None and expires < time.time()):
                    raise KeyError(key)
                super().save(record, retention_update=True)
            return super().get(key, session)

    def account_files(self, owner, session):
        return self.remote.list(owner, session)

    def delete(self, key, session):
        with self.lock:
            self.get(key, session)
            self.remote.delete(key, session)
            super().delete(key, session)

    def purge(self):
        super().purge()
        if time.time() - self.last_cloud_purge > 3600:
            try:
                self.remote.purge()
                self.last_cloud_purge = time.time()
            except HTTPException:
                # Remote reads still enforce expiry; retry without killing cleanup.
                pass

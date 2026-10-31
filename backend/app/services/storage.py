import os
import pickle
import json
import threading
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self):
        self.root = Path(os.getenv("STORAGE_DIR", "storage")).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.jobs = {}
        self.access = {}

    def path(self, key):
        try:
            uuid.UUID(key)
        except ValueError:
            raise KeyError(key)
        return self.root / f"{key}.bin"

    def retention_path(self, key):
        return self.path(key).with_suffix(".retention.json")

    @staticmethod
    def expires_at(record):
        if record.get("saved_to_account"):
            return None
        return float(record.get("expires_at", float(record["created"]) + 86400))

    def _retention(self, key):
        try:
            info = json.loads(self.retention_path(key).read_text(encoding="utf-8"))
            if info.get("file_id") != key or not isinstance(info.get("session"), str):
                return None
            if not isinstance(info.get("saved_to_account"), bool):
                return None
            if not info["saved_to_account"]:
                float(info["expires_at"])
            return info
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def metadata(self, record, size):
        frame = record.get("editor_df", record.get("df"))
        info = {
            "file_id": record["id"], "session": record["session"],
            "account_owner": record.get("account_owner"),
            "filename": record.get("filename", "Spreadsheet"),
            "saved_name": record.get("saved_name", record.get("filename", "Spreadsheet")),
            "saved_to_account": bool(record.get("saved_to_account")),
            "saved_at": record.get("saved_at"),
            "updated_at": record.get("updated_at", record["created"]),
            "expires_at": self.expires_at(record),
            "explicit_expiry": "expires_at" in record,
            "rows": len(frame) if frame is not None else 0,
            "columns": len(frame.columns) if frame is not None else 0,
            "revision": int(record.get("editor_revision", 0)),
            "size_bytes": size,
        }
        return info

    def _write_retention(self, record, size):
        info = self.metadata(record, size)
        path = self.retention_path(record["id"])
        temporary = path.with_suffix(".retention-tmp")
        temporary.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        return info

    def _apply_retention(self, record, info):
        # Retention is independent of a cleaning job's working snapshot. A job
        # started before Save/Rename must not silently revert that choice.
        if info is None:
            return
        for key in ("saved_to_account", "saved_name", "saved_at", "account_owner"):
            record[key] = info.get(key)
        if info.get("explicit_expiry"):
            record["expires_at"] = info["expires_at"]
        else:
            record.pop("expires_at", None)

    def save(self, record, *, retention_update=False):
        with self.lock:
            path = self.path(record["id"])
            if path.exists() and not retention_update:
                self._apply_retention(record, self._retention(record["id"]))
            record["updated_at"] = time.time()
            tmp = path.with_suffix(".tmp")
            with open(tmp, "wb") as handle:
                pickle.dump(record, handle)
            os.chmod(tmp, 0o600)
            # Protect a newly saved file before replacing its snapshot. If the
            # process stops between writes, retention still preserves the data.
            if record.get("saved_to_account"):
                self._write_retention(record, tmp.stat().st_size)
            tmp.replace(path)
            start = (self.expires_at(record) or (float(record["created"]) + 86400)) - 86400
            os.utime(path, (start, start))
            self._write_retention(record, path.stat().st_size)
            self.access[str(path)] = (record["session"], self.expires_at(record))

    def get(self, key, session):
        with self.lock:
            path = self.path(key)
            if not path.exists():
                raise KeyError(key)
            # Files are server-created only; clients never control serialized contents.
            with path.open("rb") as handle:
                record = pickle.load(handle)
            self._apply_retention(record, self._retention(key))
            expires = self.expires_at(record)
            self.access[str(path)] = (record["session"], expires)
            # Upgrade legacy files to expiry from upload time, not latest edit time.
            start = (expires or (float(record["created"]) + 86400)) - 86400
            os.utime(path, (start, start))
            if record["session"] != session or (expires is not None and time.time() > expires):
                raise KeyError(key)
            return record

    def check_access(self, key, session):
        """Authorize polling without deserializing the spreadsheet each time."""
        with self.lock:
            path = self.path(key)
            cached = self.access.get(str(path))
            if cached is None:
                record = self.get(key, session)
                cached = (record["session"], self.expires_at(record))
            if not path.exists() or cached[0] != session or (cached[1] is not None and time.time() > cached[1]):
                raise KeyError(key)

    def account_files(self, owner, session):
        """List bounded metadata; spreadsheet snapshots stay off the listing path."""
        with self.lock:
            files = []
            for path in self.root.glob("*.bin"):
                info = self._retention(path.stem)
                if info is None:
                    # One-time recovery for legacy or interrupted sidecar writes.
                    try:
                        with path.open("rb") as handle:
                            record = pickle.load(handle)
                        info = self._write_retention(record, path.stat().st_size)
                    except (OSError, ValueError, EOFError, pickle.UnpicklingError, KeyError, TypeError):
                        continue
                if info.get("saved_to_account") and info.get("account_owner") == owner and info.get("session") == session:
                    files.append(info)
            return sorted(files, key=lambda item: item.get("updated_at", 0), reverse=True)

    def delete(self, key, session):
        with self.lock:
            self.get(key, session)
            self.path(key).unlink(missing_ok=True)
            self.retention_path(key).unlink(missing_ok=True)
            self.path(key).with_suffix(".tmp").unlink(missing_ok=True)
            self.retention_path(key).with_suffix(".retention-tmp").unlink(missing_ok=True)
            self.access.pop(str(self.path(key)), None)
            for job_id in list(self.jobs):
                if self.jobs[job_id]["file_id"] == key:
                    del self.jobs[job_id]
            for pattern in ("*.advanced-job", "*.workflow-job"):
                for artifact in self.root.glob(pattern):
                    try:
                        if pattern == "*.workflow-job":
                            import json
                            info = json.loads(artifact.read_text(encoding="utf-8"))
                        else:
                            with artifact.open("rb") as handle: info = pickle.load(handle)
                        if info.get("file_id") == key:
                            artifact.with_suffix(".workflow-output").unlink(missing_ok=True)
                            artifact.unlink(missing_ok=True)
                    except (OSError, ValueError, EOFError, pickle.UnpicklingError, TypeError):
                        continue

    def save_job(self, job):
        with self.lock:
            target = self.root / f"{job['id']}.advanced-job"
            temporary = target.with_suffix(".advanced-tmp")
            with temporary.open("wb") as handle: pickle.dump(job, handle)
            os.chmod(temporary, 0o600); temporary.replace(target)
            os.utime(target, (job["created"], job["created"]))

    def load_job(self, key):
        uuid.UUID(key)
        target = self.root / f"{key}.advanced-job"
        if not target.exists(): return None
        with target.open("rb") as handle: job = pickle.load(handle)
        if job["status"] in ("queued", "running"):
            job.update(status="failed", error="The service restarted; your original file is preserved. Retry the operation.")
            self.save_job(job)
        return job

    def purge(self):
        with self.lock:
            for pattern in ("*.workflow-job", "*.workflow-output", "*.advanced-job", "*.tmp", "*.advanced-tmp", "*.job-tmp", "*.retention-tmp"):
                for path in self.root.glob(pattern):
                    if time.time() - path.stat().st_mtime > 86400:
                        path.unlink(missing_ok=True)
            for path in self.root.glob("*.bin"):
                info = self._retention(path.stem)
                if info is not None and info.get("saved_to_account"):
                    continue
                if info is None:
                    # Missing/corrupt metadata must never discard a saved file.
                    try:
                        with path.open("rb") as handle:
                            record = pickle.load(handle)
                        info = self._write_retention(record, path.stat().st_size)
                        if info["saved_to_account"]:
                            continue
                    except (OSError, ValueError, EOFError, pickle.UnpicklingError, KeyError, TypeError):
                        continue
                if time.time() > info["expires_at"] or time.time() - path.stat().st_mtime > 86400:
                    path.unlink(missing_ok=True)
                    self.retention_path(path.stem).unlink(missing_ok=True)
                    self.access.pop(str(path), None)
            for key in list(self.jobs):
                if time.time() - self.jobs[key]["created"] > 86400:
                    del self.jobs[key]

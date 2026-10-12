import os
import pickle
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

    def path(self, key):
        try:
            uuid.UUID(key)
        except ValueError:
            raise KeyError(key)
        return self.root / f"{key}.bin"

    def save(self, record):
        with self.lock:
            path = self.path(record["id"])
            tmp = path.with_suffix(".tmp")
            with open(tmp, "wb") as handle:
                pickle.dump(record, handle)
            os.chmod(tmp, 0o600)
            tmp.replace(path)

    def get(self, key, session):
        with self.lock:
            path = self.path(key)
            if not path.exists():
                raise KeyError(key)
            # Files are server-created only; clients never control serialized contents.
            with path.open("rb") as handle:
                record = pickle.load(handle)
            if record["session"] != session or time.time() - record["created"] > 86400:
                raise KeyError(key)
            return record

    def delete(self, key, session):
        with self.lock:
            self.get(key, session)
            self.path(key).unlink(missing_ok=True)
            for job_id in list(self.jobs):
                if self.jobs[job_id]["file_id"] == key:
                    del self.jobs[job_id]

    def purge(self):
        with self.lock:
            for path in self.root.glob("*.bin"):
                if time.time() - path.stat().st_mtime > 86400:
                    path.unlink(missing_ok=True)
            for key in list(self.jobs):
                if time.time() - self.jobs[key]["created"] > 86400:
                    del self.jobs[key]

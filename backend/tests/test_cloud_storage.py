import copy
import hashlib
import time
import uuid
import pandas as pd
import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from app.services.cloud_storage import CloudStore, SupabaseSnapshots
from app.services.static_site import install_static_site


class MemoryRemote:
    def __init__(self):
        self.records = {}
        self.info = {}
        self.fail = False
    def write(self, record, info):
        if self.fail:
            raise HTTPException(503, "offline")
        self.records[record["id"]] = copy.deepcopy(record)
        self.info[record["id"]] = copy.deepcopy(info)
    def read(self, key, session):
        record = self.records[key]
        if record["session"] != session:
            raise KeyError(key)
        return copy.deepcopy(record)
    def list(self, owner, session):
        return [copy.deepcopy(i) for i in self.info.values() if i["saved_to_account"] and i["account_owner"] == owner and i["session"] == session]
    def delete(self, key, session):
        self.read(key, session)
        del self.records[key]
        del self.info[key]
    def purge(self):
        pass


def item():
    owner = str(uuid.uuid4())
    return {"id": str(uuid.uuid4()), "account_owner": owner,
            "session": hashlib.sha256(("account:"+owner).encode()).hexdigest(),
            "created": time.time(), "filename": "test.csv",
            "original_bytes": b"x\n 1 ", "df": pd.DataFrame({"x": [" 1 "]}),
            "editor_df": pd.DataFrame({"x": ["1"]}), "saved_to_account": True}


def test_survives_empty_local_disk_with_original_and_edits(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "first"))
    remote = MemoryRemote()
    store = CloudStore(remote)
    record = item()
    store.save(record)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "restarted"))
    restarted = CloudStore(remote)
    assert restarted.account_files(record["account_owner"], record["session"])[0]["file_id"] == record["id"]
    restored = restarted.get(record["id"], record["session"])
    assert restored["original_bytes"] == record["original_bytes"]
    assert restored["editor_df"].iloc[0,0] == "1"
    with pytest.raises(KeyError):
        restarted.get(record["id"], "other-account")
    restarted.delete(record["id"], record["session"])
    assert not remote.records


def test_failed_cloud_commit_does_not_change_local_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    remote = MemoryRemote()
    store = CloudStore(remote)
    record = item()
    store.save(record)
    record["editor_df"].iloc[0,0] = "changed"
    remote.fail = True
    with pytest.raises(HTTPException):
        store.save(record)
    assert store.get(record["id"], record["session"])["editor_df"].iloc[0,0] == "1"


def test_expired_remote_copy_cannot_be_restored(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    remote = MemoryRemote()
    record = item()
    record.update(saved_to_account=False, expires_at=time.time()-1)
    remote.write(record, {})
    with pytest.raises(KeyError):
        CloudStore(remote).get(record["id"], record["session"])


def test_snapshot_signature_and_identity_checked_before_restore(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-only")
    monkeypatch.setenv("STORAGE_SIGNING_KEY", "test-only-signing-key-not-for-deployment")
    remote = SupabaseSnapshots()
    record = item()
    encoded = remote.encode(record)
    assert remote.decode(encoded, record["id"], record["session"])["original_bytes"] == record["original_bytes"]
    for payload, key, session in [("0"*64+encoded[64:],record["id"],record["session"]),
                                  (encoded,str(uuid.uuid4()),record["session"]),
                                  (encoded,record["id"],"wrong")]:
        with pytest.raises(HTTPException):
            remote.decode(payload,key,session)


def test_exported_routes_and_missing_api(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("cover")
    (tmp_path / "workspace.html").write_text("workspace")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    app = FastAPI()
    install_static_site(app)
    client = TestClient(app)
    assert client.get("/").text == "cover"
    assert client.get("/workspace").text == "workspace"
    assert client.get("/api/missing").status_code == 404
    assert client.get("/missing.js").status_code == 404

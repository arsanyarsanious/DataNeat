import copy
import hashlib
import json
import os
import time
import uuid

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.storage import Store


def account_session(owner):
    return hashlib.sha256(("account:" + owner).encode()).hexdigest()


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    return Store()


def record(owner="alice", created=None):
    return {
        "id": str(uuid.uuid4()), "session": account_session(owner),
        "account_owner": owner, "created": time.time() if created is None else created,
        "filename": "customers.csv", "original_bytes": b"Name\n Cairo \n",
        "df": pd.DataFrame({"Name": [" Cairo "]}),
        "editor_df": pd.DataFrame({"Name": ["Cairo"]}), "editor_revision": 1,
        "workflow_steps": [{"id": "step-one", "kind": "fix"}],
        "complete_changes": [{"before": " Cairo ", "after": "Cairo"}],
    }


def persist_saved(store, item):
    item.update(saved_to_account=True, saved_name="My cleaned customers", saved_at=time.time())
    store.save(item, retention_update=True)


def test_saved_record_survives_expiry_purge_restart_and_keeps_original_history(isolated_store):
    item = record(created=time.time() - 3 * 86400)
    persist_saved(isolated_store, item)
    isolated_store.purge()
    restarted = Store()
    actual = restarted.get(item["id"], item["session"])
    assert actual["original_bytes"] == item["original_bytes"]
    assert actual["df"].iloc[0, 0] == " Cairo "
    assert actual["editor_df"].iloc[0, 0] == "Cairo"
    assert actual["workflow_steps"] == item["workflow_steps"]
    assert actual["complete_changes"] == item["complete_changes"]
    restarted.check_access(item["id"], item["session"])
    with pytest.raises(KeyError):
        restarted.get(item["id"], account_session("bob"))


def test_temporary_record_expiry_and_restarted_poll_access(isolated_store):
    item = record(created=time.time() - 86401)
    isolated_store.save(item)
    with pytest.raises(KeyError):
        Store().get(item["id"], item["session"])
    isolated_store.purge()
    assert not isolated_store.path(item["id"]).exists()
    assert not isolated_store.retention_path(item["id"]).exists()


def test_switch_to_temporary_gives_fresh_day_without_expiring_original_history(isolated_store):
    item = record(created=time.time() - 3 * 86400)
    persist_saved(isolated_store, item)
    now = time.time()
    item.update(saved_to_account=False, expires_at=now + 86400)
    isolated_store.save(item, retention_update=True)
    restarted = Store()
    restarted.purge()
    assert restarted.get(item["id"], item["session"])["complete_changes"] == item["complete_changes"]
    assert restarted.account_files("alice", item["session"]) == []
    item["expires_at"] = now - 1
    isolated_store.save(item, retention_update=True)
    with pytest.raises(KeyError):
        isolated_store.check_access(item["id"], item["session"])
    isolated_store.purge()
    assert not isolated_store.path(item["id"]).exists()


@pytest.mark.parametrize("broken_sidecar", ["missing", "corrupt"])
def test_missing_or_corrupt_retention_metadata_cannot_purge_saved_file(isolated_store, broken_sidecar):
    item = record(created=time.time() - 3 * 86400)
    persist_saved(isolated_store, item)
    sidecar = isolated_store.retention_path(item["id"])
    if broken_sidecar == "missing":
        sidecar.unlink()
    else:
        sidecar.write_text("not-json", encoding="utf-8")
    isolated_store.purge()
    assert isolated_store.path(item["id"]).exists()
    assert isolated_store.account_files("alice", item["session"])[0]["saved_name"] == "My cleaned customers"


def test_library_reads_metadata_without_deserializing_spreadsheets(isolated_store, monkeypatch):
    item = record()
    persist_saved(isolated_store, item)
    other = record("bob")
    persist_saved(isolated_store, other)
    import app.services.storage as storage

    def no_spreadsheet_load(*_):
        raise AssertionError("Library listing should only read small metadata sidecars")

    monkeypatch.setattr(storage.pickle, "load", no_spreadsheet_load)
    files = isolated_store.account_files("alice", item["session"])
    assert len(files) == 1 and files[0]["file_id"] == item["id"]
    assert files[0]["rows"] == 1 and files[0]["columns"] == 1


def test_cleaning_snapshot_cannot_revert_save_rename_or_temporary_choice(isolated_store):
    item = record()
    isolated_store.save(item)
    stale = copy.deepcopy(item)
    persist_saved(isolated_store, item)
    item["saved_name"] = "Renamed"
    isolated_store.save(item, retention_update=True)
    stale["editor_revision"] = 2
    isolated_store.save(stale)
    current = isolated_store.get(item["id"], item["session"])
    assert current["saved_to_account"] and current["saved_name"] == "Renamed"
    assert current["editor_revision"] == 2
    stale_saved = copy.deepcopy(current)
    current.update(saved_to_account=False, expires_at=time.time() + 86400)
    isolated_store.save(current, retention_update=True)
    isolated_store.save(stale_saved)
    after = isolated_store.get(item["id"], item["session"])
    assert not after["saved_to_account"]
    assert after["expires_at"] == current["expires_at"]


def test_delete_removes_snapshot_metadata_and_related_job_artifacts(isolated_store):
    item = record()
    persist_saved(isolated_store, item)
    job_id = str(uuid.uuid4())
    artifact = isolated_store.root / (job_id + ".workflow-job")
    output = isolated_store.root / (job_id + ".workflow-output")
    artifact.write_text(json.dumps({"file_id": item["id"]}), encoding="utf-8")
    output.write_bytes(b"csv-output")
    isolated_store.delete(item["id"], item["session"])
    assert not isolated_store.path(item["id"]).exists()
    assert not isolated_store.retention_path(item["id"]).exists()
    assert not artifact.exists() and not output.exists()


@pytest.fixture
def account_api(tmp_path, monkeypatch):
    import app.main as main
    main.store.root = tmp_path
    main.store.jobs.clear()
    main.store.access.clear()
    main.rate.clear()
    monkeypatch.setattr(main.identity, "configuration", lambda: {"enabled": True})

    def verify(token):
        if token not in ("alice", "bob"):
            raise HTTPException(401, "Please sign in to continue.")
        return {"id": token, "email": token + "@example.com"}

    monkeypatch.setattr(main.identity, "verify", verify)
    monkeypatch.setattr(main.identity, "record", lambda *_: None)

    def browser(user=None):
        client = TestClient(main.app)
        if user:
            client.cookies.set("dataneat_auth", user)
        return client

    return browser, main


def api_upload(client):
    response = client.post("/api/files/upload", files={"file": ("source.csv", b"ID,Name\n001,Cairo\n002,Aswan\n", "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()["file_id"]


def test_account_library_is_shared_across_verified_same_account_browsers_only(account_api):
    browser, main = account_api
    alice = browser("alice")
    second_alice = browser("alice")
    bob = browser("bob")
    fid = api_upload(alice)
    response = alice.post(f"/api/account/files/{fid}/save", json={"name": "My customers"})
    assert response.status_code == 200, response.text
    assert response.json()["saved"] and response.json()["saved_to_account"] and response.json()["expires_at"] is None
    assert alice.cookies.get("dataneat_session") != second_alice.cookies.get("dataneat_session")
    listing = second_alice.get("/api/account/files")
    assert listing.status_code == 200, listing.text
    assert listing.json()["files"][0]["saved_name"] == "My customers"
    assert second_alice.get(f"/api/files/{fid}/profile").status_code == 200
    assert second_alice.get(f"/api/account/files/{fid}/status").json()["file_id"] == fid
    assert bob.get("/api/account/files").json()["files"] == []
    for path in (f"/api/account/files/{fid}", f"/api/files/{fid}/profile"):
        assert bob.get(path).status_code == 404
    for action in ("save", "temporary", "rename"):
        assert bob.post(f"/api/account/files/{fid}/{action}", json={"name": "Stolen"}).status_code == 404
    assert bob.delete(f"/api/account/files/{fid}").status_code == 404
    assert browser().get("/api/account/files").status_code == 401
    owner = main.store.get(fid, account_session("alice"))
    assert owner["account_owner"] == "alice"


def test_account_api_save_keeps_workflow_and_rename_then_temporary_and_delete(account_api):
    browser, main = account_api
    alice = browser("alice")
    fid = api_upload(alice)
    assert alice.post(f"/api/files/{fid}/workflow/init").status_code == 200
    original = main.store.get(fid, account_session("alice"))
    original["editor_revision"] = 3
    original["workflow_steps"] = [{"id": "manual-one", "kind": "fix"}]
    original["complete_changes"] = [{"before": "CAIRO", "after": "Cairo"}]
    main.store.save(original)
    assert alice.post(f"/api/account/files/{fid}/save").status_code == 200
    renamed = alice.post(f"/api/account/files/{fid}/rename", json={"name": "  Quarterly customers  "})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["saved_name"] == "Quarterly customers"
    current = main.store.get(fid, account_session("alice"))
    assert current["filename"] == "source.csv" and current["editor_revision"] == 3
    assert current["workflow_steps"] == original["workflow_steps"]
    assert current["complete_changes"] == original["complete_changes"]
    assert current["original_bytes"] == original["original_bytes"]
    old_time = time.time() - 3 * 86400
    os.utime(main.store.path(fid), (old_time, old_time))
    main.store.purge()
    assert main.store.path(fid).exists()
    temporary = alice.post(f"/api/account/files/{fid}/temporary")
    assert temporary.status_code == 200, temporary.text
    assert not temporary.json()["saved_to_account"]
    assert abs(temporary.json()["expires_at"] - time.time() - 86400) < 3
    assert alice.get("/api/account/files").json()["files"] == []
    assert alice.delete(f"/api/account/files/{fid}").status_code == 200
    assert alice.get(f"/api/files/{fid}/profile").status_code == 404


def test_account_save_limits_names_and_storage_are_enforced(account_api, monkeypatch):
    browser, _ = account_api
    alice = browser("alice")
    fid = api_upload(alice)
    for name in ("", "   ", "bad\nname", "a" * 161):
        assert alice.post(f"/api/account/files/{fid}/save", json={"name": name}).status_code == 422
    monkeypatch.setenv("MAX_ACCOUNT_FILES", "1")
    assert alice.post(f"/api/account/files/{fid}/save").status_code == 200
    second = api_upload(alice)
    assert alice.post(f"/api/account/files/{second}/save").status_code == 409
    assert alice.get("/api/account/files").json()["storage"]["max_saved_files"] == 1
    assert alice.delete(f"/api/account/files/{fid}").status_code == 200
    assert alice.post(f"/api/account/files/{second}/save").status_code == 200


def test_local_unsigned_visitors_cannot_create_fake_accounts(account_api, monkeypatch):
    browser, main = account_api
    monkeypatch.setattr(main.identity, "configuration", lambda: {"enabled": False})
    visitor = browser()
    fid = api_upload(visitor)
    assert visitor.get("/api/account/files").status_code == 401
    assert visitor.post(f"/api/account/files/{fid}/save", json={"name": "Fake account"}).status_code == 401
    assert visitor.get(f"/api/files/{fid}/profile").status_code == 200


def test_account_storage_bytes_quota_does_not_partially_save(account_api, monkeypatch):
    browser, main = account_api
    alice = browser("alice")
    fid = api_upload(alice)
    item = main.store.get(fid, account_session("alice"))
    item["original_bytes"] = b"x" * (1024 * 1024 + 1)
    main.store.save(item)
    monkeypatch.setenv("MAX_ACCOUNT_STORAGE_MB", "1")
    response = alice.post(f"/api/account/files/{fid}/save")
    assert response.status_code == 409, response.text
    assert not alice.get(f"/api/account/files/{fid}/status").json()["saved"]
    assert alice.get("/api/account/files").json()["files"] == []


def test_workspace_temporary_discard_preserves_saved_file_but_deletes_temporary(account_api):
    browser, _ = account_api
    alice = browser("alice")
    saved_id = api_upload(alice)
    assert alice.post(f"/api/account/files/{saved_id}/save").status_code == 200
    response = alice.delete(f"/api/files/{saved_id}?only_temporary=true")
    assert response.status_code == 200, response.text
    assert alice.get(f"/api/files/{saved_id}/workspace").status_code == 200
    assert alice.get(f"/api/account/files/{saved_id}/status").json()["saved"]
    assert [item["file_id"] for item in alice.get("/api/account/files").json()["files"]] == [saved_id]

    temporary_id = api_upload(alice)
    response = alice.delete(f"/api/files/{temporary_id}?only_temporary=true")
    assert response.status_code == 200, response.text
    assert alice.get(f"/api/files/{temporary_id}/workspace").status_code == 404
    assert [item["file_id"] for item in alice.get("/api/account/files").json()["files"]] == [saved_id]

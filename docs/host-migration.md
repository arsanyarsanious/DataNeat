# Host migration preparation (deferred work)

Moving DataNeat to a host that allows more than one web worker is deliberately
not part of the 2026-11-23 release. Capacity was raised inside the current
single-worker envelope instead. The following items are required before running
`uvicorn --workers 2+`; they are recorded here so the migration starts from a
known list rather than a guess.

## Why it is not safe yet

The deployed process keeps coordination state in memory:

- `services/workflow_jobs.py` keeps the job registry in a module-level `jobs`
  dict and guards commits with `store.lock`, a `threading.RLock`.
- Revision compare-and-set happens in Python: the job reads the record, checks
  `editor_revision`, then calls `store.save` under that process-local lock.
- `main.py` keeps `editor_tasks` and the per-IP rate limiter in memory.
- `services/storage.py` and `cloud_storage.py` write local snapshot files; the
  cloud path's docstring says "single-instance" for the same reason.

Two workers would therefore allow two commits from the same starting revision
to both succeed, and the in-memory caches would diverge.

## Required changes, in order

1. **Atomic revision CAS in the database.** Extend the `dataneat_commit_file`
   RPC to accept the expected revision and perform the update with
   `WHERE ... AND revision = expected`, returning the new revision or a
   conflict. Python must treat a conflict as a 409, never retry silently.
2. **Cross-process local locking.** For the local `Store`, replace
   `threading.RLock` for commit/retention paths with an OS file lock (POSIX
   `fcntl`, Windows `msvcrt`) around read-modify-write. Keep the thread lock
   as the fast path.
3. **Job registry.** The registry is already persisted as JSON per job; make
   recovery read-through and make queued/running counts safe across processes
   (or move admission to the database). Do not let each worker start its own
   unbounded pool.
4. **Per-process caches.** Confirm `editor_tasks` recomputes safely in another
   worker (it currently caches only prepared futures) and either accept the
   duplicate work or persist the prepared copy.
5. **Rate limiting.** A shared counter is optional at beta scale; document that
   limits are per worker if it stays in memory.
6. **Cleanup loop.** `purge()` runs every 60 seconds per worker; verify it is
   idempotent under concurrent deletes (it tolerates missing files).
7. **Tests.** Add a two-thread, two-store commit race: same expected revision,
   exactly one success and one 409; job recovery after restart; share links
   still resolve through `get_shared` with no session.

## Host candidates (no card)

- Hugging Face Spaces CPU basic: 2 vCPU / 16 GB RAM, Docker, no card. Public
  Space repository; static export can be served by the same FastAPI app via
  `STATIC_DIR`, keeping Supabase as the storage backend. Cold start applies
  after inactivity.
- PythonAnywhere Developer ($10/month): 3 workers, but paid and against the
  current no-card preference.

# Upload reliability and off-request analysis

## Incident (2026-11-24)

Hosted CSV uploads failed with “Server returned an invalid response”. The
PythonAnywhere access log showed the actual request result:

```
POST /api/files/upload 504 response-time=60.039
```

The host proxy terminates any request at 60 seconds with an HTML 504 page. The
upload endpoint was doing parsing, full profiling and the cleaning plan in one
request; for larger CSVs this exceeded 60s, so the browser could not parse the
response.

Benchmarked profiling time on the host:

| Cells | Profile time |
|---|---|
| 50,000 | 15.2 s |
| 150,000 | 48.9 s |
| 240,000 | exceeded 60 s |

With parsing and the cloud snapshot save added, the practical ceiling was well
below the advertised 250,000-cell budget.

## Fix

- Uploads larger than `ANALYSIS_SYNC_CELLS` (default 40,000) return immediately
  with the file ID, preview and metadata plus `analysis_pending: true`.
- Profiling and the default cleaning plan run in a FastAPI background task after
  the response, so the host's 60-second request ceiling no longer applies.
- `GET /api/files/{id}/analysis` returns `202 {"status":"pending"}` while work is
  running, then `200 {"status":"ready","profile":...,"plan":...}`. It is
  idempotent and re-queues work if the worker restarted mid-analysis.
- The frontend shows “Preparing your data summary…”, polls until ready, then
  opens Explore normally. Small files still take the instant synchronous path.
- Pending records also restore correctly after a page reload.
- Failures are persisted as a clean JSON error instead of a half-response.

## Additional defect fixed

Starlette 1.x limits each multipart part to 1 MiB, so files between 1 MiB and
the advertised 5 MiB were rejected with `400 There was an error parsing the
body`. `Request.form()` is now invoked with the real upload budget
(`MAX_UPLOAD + 1 MiB`) so the app honors its own limit.

## Upload errors

The workspace upload handler now reports the HTTP status when a proxy returns a
non-JSON page, and the API has a JSON handler for unexpected exceptions, so a
future failure is diagnosable instead of “invalid response”.

## Upload latency (2026-11-24)

The access log also showed uploads taking ~8.8s before analysis even started,
even though profiling was deferred. That wait was the remote cloud snapshot
commit. The upload path now writes only the local temporary snapshot and
returns; the background analysis performs the durable cloud commit. Hosted
workspaces set `ANALYSIS_SYNC_CELLS=0`, so every upload takes the fast path.
Polling is 500ms for the first 8 seconds, then 1.5s.

Large-sheet analysis remains CPU-bound on the free single worker (tens of
seconds), but the upload response no longer waits for it and the UI shows an
explicit preparation state.

- 732 backend tests pass, including new tests for pending-then-ready analysis,
  queued analysis polling and >1 MiB multipart uploads.
- Local browser run: 240k-cell CSV returned immediately, showed “Preparing your
  data summary…”, became ready in about 35s with no page errors; a 40-row file
  still opened in ~0.3s.
- The host was verified to execute background tasks after responding.
- Live static and backend deployment completed with 200 responses.

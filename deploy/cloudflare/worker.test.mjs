import test from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.mjs";

test("static assets and missing backend are reported correctly", async () => {
  const assets = { fetch: () => new Response("app") };
  assert.equal(
    await (
      await worker.fetch(new Request("https://app.example/"), {
        ASSETS: assets,
      })
    ).text(),
    "app",
  );
  assert.equal(
    (await worker.fetch(new Request("https://app.example/api/health"), {}))
      .status,
    503,
  );
  assert.equal(
    (
      await worker.fetch(new Request("https://app.example/api/health"), {
        BACKEND_ORIGIN: "http://bad.example",
      })
    ).status,
    503,
  );
});

test("API forwards body, session cookie, query and response cookies without caching", async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = async (request) => {
    assert.equal(
      request.url,
      "https://backend.example/api/files/upload?sheet=A",
    );
    assert.equal(request.headers.get("Cookie"), "session=private");
    assert.equal(await request.text(), "upload");
    return new Response("ok", {
      headers: { "Set-Cookie": "session=private; Secure; HttpOnly" },
    });
  };
  try {
    const request = new Request(
      "https://app.example/api/files/upload?sheet=A",
      {
        method: "POST",
        body: "upload",
        headers: { Cookie: "session=private", Origin: "https://app.example" },
      },
    );
    const response = await worker.fetch(request, {
      BACKEND_ORIGIN: "https://backend.example",
    });
    assert.equal(await response.text(), "ok");
    assert.match(response.headers.get("Set-Cookie"), /HttpOnly/);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  } finally {
    globalThis.fetch = saved;
  }
});

test("cross-origin changes are rejected and upstream failures are explained", async () => {
  assert.equal(
    (
      await worker.fetch(
        new Request("https://app.example/api/clean", {
          method: "POST",
          headers: { Origin: "https://other.example" },
        }),
        { BACKEND_ORIGIN: "https://backend.example" },
      )
    ).status,
    403,
  );
  const saved = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("offline");
  };
  try {
    assert.equal(
      (
        await worker.fetch(new Request("https://app.example/api/health"), {
          BACKEND_ORIGIN: "https://backend.example",
        })
      ).status,
      502,
    );
  } finally {
    globalThis.fetch = saved;
  }
});

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
    if (!env.BACKEND_ORIGIN)
      return Response.json(
        { detail: "The cleaning backend has not been connected yet." },
        { status: 503 },
      );
    let backend;
    try {
      backend = new URL(env.BACKEND_ORIGIN);
      if (
        backend.protocol !== "https:" ||
        backend.pathname !== "/" ||
        backend.username ||
        backend.password
      )
        throw new Error("Invalid backend");
    } catch {
      return Response.json(
        { detail: "Backend configuration must be an HTTPS server origin." },
        { status: 503 },
      );
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      const origin = request.headers.get("Origin");
      if (origin && origin !== url.origin)
        return Response.json(
          { detail: "Cross-origin modifications are not allowed." },
          { status: 403 },
        );
    }
    const destination = new URL(url.pathname + url.search, backend.origin);
    const headers = new Headers(request.headers);
    headers.delete("Host");
    try {
      const upstream = await fetch(
        new Request(destination, {
          method: request.method,
          headers,
          body: ["GET", "HEAD"].includes(request.method)
            ? undefined
            : request.body,
          redirect: "manual",
          duplex: "half",
        }),
      );
      const response = new Response(upstream.body, upstream);
      response.headers.set("Cache-Control", "no-store");
      return response;
    } catch {
      return Response.json(
        { detail: "The cleaning backend is temporarily unavailable." },
        { status: 502 },
      );
    }
  },
};

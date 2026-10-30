import type { NextRequest } from "next/server";
import { Agent } from "undici";

export const runtime = "nodejs";
const ROUTES: Readonly<
  Record<string, { method: "GET" | "POST"; segments: number }>
> = {
  catalog: { method: "GET", segments: 1 },
  questions: { method: "GET", segments: 1 },
  metrics: { method: "GET", segments: 1 },
  changes: { method: "POST", segments: 1 },
  chat: { method: "POST", segments: 1 },
  feedback: { method: "POST", segments: 1 },
  documents: { method: "GET", segments: 2 },
  guidance: { method: "GET", segments: 1 },
  observability: { method: "GET", segments: 2 },
};
const MAX_BODY_BYTES = 256 * 1024;
const backendAgent = new Agent({
  headersTimeout: 600_000,
  bodyTimeout: 600_000,
  connect: { timeout: 5_000 },
});

async function limitedBody(
  request: NextRequest,
  signal: AbortSignal,
): Promise<Uint8Array | null> {
  const declared = Number(request.headers.get("content-length") || "0");
  if (declared > MAX_BODY_BYTES) return null;
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks: Uint8Array[] = [];
  let length = 0;
  const cancel = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal.addEventListener("abort", cancel, { once: true });
  try {
    while (true) {
      signal.throwIfAborted();
      const { value, done } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_BODY_BYTES) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    signal.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
  const result = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const route = Object.hasOwn(ROUTES, path[0]) ? ROUTES[path[0]] : undefined;
  if (!route || path.length !== route.segments)
    return Response.json({ detail: "Not found" }, { status: 404 });
  if (request.method !== route.method)
    return Response.json(
      { detail: "Method not allowed" },
      { status: 405, headers: { Allow: route.method } },
    );
  if (
    path[0] === "documents" &&
    (!/^[^/\\\u0000-\u001f]+\.pdf$/i.test(path[1]) ||
      path[1] === "." ||
      path[1] === "..")
  )
    return Response.json({ detail: "Document not found" }, { status: 404 });
  const deadline = AbortSignal.timeout(
    path[0] === "feedback"
      ? 30_000
      : path[0] === "chat"
        ? 45_000
        : path[0] === "catalog" || path[0] === "questions"
          ? 15_000
          : 600_000,
  );
  const signal = AbortSignal.any([request.signal, deadline]);
  try {
    let body: Uint8Array | undefined;
    if (route.method === "POST") {
      if (
        request.headers
          .get("content-type")
          ?.split(";", 1)[0]
          .trim()
          .toLowerCase() !== "application/json"
      )
        return Response.json(
          { detail: "Send a JSON request body." },
          { status: 415 },
        );
      const bytes = await limitedBody(request, signal);
      if (bytes === null)
        return Response.json(
          { detail: "Request body exceeds the allowed size." },
          { status: 413 },
        );
      body = bytes;
    }
    const base = process.env.FINSIGHT_API_URL || "http://127.0.0.1:8000";
    const configured = new URL(base);
    if (
      !["http:", "https:"].includes(configured.protocol) ||
      configured.username ||
      configured.password ||
      configured.search ||
      configured.hash
    )
      return Response.json(
        { detail: "The research service URL is misconfigured." },
        { status: 503 },
      );
    const url = new URL(
      path.map(encodeURIComponent).join("/"),
      base.replace(/\/$/, "") + "/",
    );
    url.search = request.nextUrl.search;
    const upstream = await fetch(url, {
      dispatcher: backendAgent,
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        // Shared secret and original client address for backend auth/rate limits.
        ...(process.env.FINSIGHT_API_KEY
          ? { "X-API-Key": process.env.FINSIGHT_API_KEY }
          : {}),
        ...(request.headers.get("x-forwarded-for")
          ? { "X-Forwarded-For": request.headers.get("x-forwarded-for")! }
          : {}),
      },
      body: body === undefined ? undefined : Buffer.from(body),
      cache: "no-store",
      signal,
    } as RequestInit & { dispatcher: Agent });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        ...(upstream.headers.get("Retry-After")
          ? { "Retry-After": upstream.headers.get("Retry-After")! }
          : {}),
      },
    });
  } catch {
    return Response.json(
      {
        detail:
          "The research service is unavailable or timed out. Check the backend and retry.",
      },
      { status: deadline.aborted ? 504 : 503 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;

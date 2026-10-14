export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiRequest<T>(
  path: string,
  options: {
    signal?: AbortSignal;
    timeoutMs?: number;
    body?: unknown;
    decode: (value: unknown) => T;
  },
): Promise<T> {
  const endpoint = path.split(/[/?]/, 1)[0];
  const timeoutMs =
    options.timeoutMs ??
    (endpoint === "feedback"
      ? 30_000
      : endpoint === "chat"
        ? 45_000
        : endpoint === "catalog" || endpoint === "questions"
          ? 15_000
          : 600_000);
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0)
    throw new Error("Request timeout must be a positive integer.");
  const deadline = AbortSignal.timeout(timeoutMs);
  const signal = options.signal
    ? AbortSignal.any([options.signal, deadline])
    : deadline;
  try {
    let response: Response;
    try {
      response = await fetch(`/api/${path}`, {
        method: options.body === undefined ? "GET" : "POST",
        headers:
          options.body === undefined
            ? undefined
            : { "Content-Type": "application/json" },
        signal,
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
        cache: "no-store",
      });
    } catch (error) {
      if (signal.aborted) throw error;
      throw new ApiError(
        "Could not connect to the research service. Check your connection and retry.",
        503,
      );
    }
    let value: unknown;
    try {
      value = await response.json();
    } catch {
      throw new ApiError(
        "The research service returned an unreadable response. Please retry.",
        response.status,
      );
    }
    if (!response.ok) {
      const detail =
        value && typeof value === "object" && "detail" in value
          ? (value as { detail: unknown }).detail
          : null;
      throw new ApiError(
        typeof detail === "string"
          ? detail
          : response.status === 404
            ? "The research endpoint was not found. Check that FINSIGHT_API_URL points to the Finsight backend, then restart the frontend."
            : "The request could not be processed. Check your inputs and retry.",
        response.status,
      );
    }
    return options.decode(value);
  } catch (error) {
    // Caller cancellation must keep its identity for stale-response guards.
    if (options.signal?.aborted) throw options.signal.reason;
    if (deadline.aborted)
      throw new ApiError(
        "The request timed out. Please retry; response times can vary.",
        504,
      );
    throw error;
  }
}

export function downloadJson(value: unknown, filename: string): void {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

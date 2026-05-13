// Thin fetch wrapper that injects the X-API-Key header and parses JSON.
// All calls flow through nginx → FastAPI in production; in dev, VITE_API_BASE_URL
// can be overridden to hit a local API directly.

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY ?? "devkey-please-change";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
  ) {
    super(`${status} ${body}`);
    this.name = "ApiError";
  }
}

function buildUrl(path: string, params?: Record<string, unknown>): string {
  // Always treat the API path as relative to the configured base.
  // window.location.origin is the right anchor for both absolute and relative
  // bases — the URL constructor handles both consistently.
  const url = new URL(API_BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v != null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, unknown>,
): Promise<T> {
  const res = await fetch(buildUrl(path, params), {
    headers: { "X-API-Key": API_KEY },
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return (await res.json()) as T;
}

export async function apiPost<TReq, TRes>(
  path: string,
  body: TReq,
): Promise<TRes> {
  const res = await fetch(buildUrl(path), {
    method: "POST",
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return (await res.json()) as TRes;
}

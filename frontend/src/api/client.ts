/** Fetch wrapper. Treats 404 as empty data, surfaces other errors. */

const BASE = "/api"; // proxied to localhost:7779 in dev (vite.config.ts)

export class ApiError extends Error {
  constructor(public status: number, public path: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const resp = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(init.headers || {}),
    },
  });

  if (resp.status === 404) {
    // Several legacy widget endpoints aren't implemented yet — let the UI
    // gracefully render an empty state instead of an error.
    return [] as unknown as T;
  }

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new ApiError(resp.status, path, `HTTP ${resp.status}: ${text || resp.statusText}`);
  }

  return resp.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

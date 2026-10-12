// Vercel Routing Middleware: password-gates the private admin area of the static site.
//   /admin, /admin/*      the admin page and its private code chunks (vite.config.ts emits them to /admin/chunks/)
//   /api/admin/*          the private data files written by scripts/export_snapshot.py
// Everything else (the public site) never reaches this function. HTTP Basic auth, any username; the password
// is the ADMIN_PASSWORD environment variable of the Vercel project. If it is unset every request is refused.
export const config = { matcher: ["/admin", "/admin/:path*", "/api/admin/:path*"] };

const enc = new TextEncoder();

// Compare without bailing out at the first different byte.
export function same(a: string, b: string): boolean {
  const x = enc.encode(a);
  const y = enc.encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

// The password out of an "Authorization: Basic base64(user:password)" header; null if it isn't one.
export function passwordFrom(header: string | null): string | null {
  if (!header?.startsWith("Basic ")) return null;
  try {
    const decoded = atob(header.slice(6));
    const colon = decoded.indexOf(":");
    return colon < 0 ? null : decoded.slice(colon + 1);
  } catch {
    return null;
  }
}

export default function middleware(request: Request): Response {
  const expected = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.ADMIN_PASSWORD;
  const given = passwordFrom(request.headers.get("authorization"));
  if (expected && given !== null && same(given, expected)) {
    return new Response(null, { headers: { "x-middleware-next": "1" } }); // let the request continue
  }
  return new Response("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="ARC admin", charset="UTF-8"', "Cache-Control": "no-store" },
  });
}

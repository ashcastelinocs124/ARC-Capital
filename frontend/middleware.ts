// Vercel Routing Middleware: password-gates the private admin area of the static site.
//   /admin, /admin/*      the admin page and its private code chunks (vite.config.ts emits them to /admin/chunks/)
//   /api/admin/*          the private data files (scripts/export_snapshot.py) and, via /api/admin/live/*, the Fly API
// Everything else (the public site) never reaches this function. The password is the ADMIN_PASSWORD environment
// variable of the Vercel project; if it is unset every request is refused.
//
// Sign-in: /admin/login (a page in the app) posts the password to /api/admin/session, which sets `arc_admin`, a
// 12-hour session cookie signed with HMAC-SHA256 keyed by ADMIN_PASSWORD (so changing the password signs everyone
// out). The Fly API (src/castelino/dashboard/desk_app.py) checks the same cookie. HTTP Basic still works, for curl.
// Without either, a page request is redirected to the sign-in page and anything else gets a plain 401 (no
// WWW-Authenticate, so the browser's own password popup never shows).
export const config = { matcher: ["/admin", "/admin/:path*", "/api/admin/:path*"] };

const COOKIE = "arc_admin";
const TTL = 12 * 3600; // seconds
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

const b64url = (buf: ArrayBuffer) =>
  btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

// Signature of a session that expires at `exp` (unix seconds). Must match desk_app.session_sig().
export async function sign(exp: number, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(`${COOKIE}.${exp}`)));
}

// The session's expiry if the Cookie header carries a valid, unexpired one; else null.
export async function sessionExpiry(cookies: string | null, secret: string, now = Date.now() / 1000): Promise<number | null> {
  const value = cookies?.split(/;\s*/).find((c) => c.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1);
  const [exp, sig] = value?.split(".") ?? [];
  const e = Number(exp);
  if (!sig || !Number.isInteger(e) || e < now) return null;
  return same(sig, await sign(e, secret)) ? e : null;
}

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers } });
const cookie = (value: string, maxAge: number) => `${COOKIE}=${value}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;
const next = () => new Response(null, { headers: { "x-middleware-next": "1" } }); // let the request continue

async function signIn(request: Request, secret: string | undefined): Promise<Response> {
  if (!secret) return json(503, { detail: "Admin sign-in isn't set up on this site." });
  // JSON only: a cross-site form can't send it, so nobody can sign a visitor in from another page
  if (!request.headers.get("content-type")?.startsWith("application/json")) return json(415, { detail: "Send JSON." });
  const body = (await request.json().catch(() => null)) as { password?: unknown } | null;
  const given = typeof body?.password === "string" ? body.password : "";
  if (!same(given, secret)) {
    await new Promise((r) => setTimeout(r, 500)); // slows guessing
    return json(401, { detail: "That password isn't right." });
  }
  const exp = Math.floor(Date.now() / 1000) + TTL;
  return json(200, { expires: exp }, { "Set-Cookie": cookie(`${exp}.${await sign(exp, secret)}`, TTL) });
}

export default async function middleware(request: Request): Promise<Response> {
  const secret = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.ADMIN_PASSWORD || undefined;
  const { pathname, search } = new URL(request.url);

  if (pathname === "/api/admin/session" && request.method === "POST") return signIn(request, secret);
  if (pathname === "/api/admin/logout" && request.method === "POST") return json(200, { ok: true }, { "Set-Cookie": cookie("", 0) });
  if (pathname === "/admin/login" || pathname === "/admin/login/") return next(); // the sign-in page itself is public

  const basic = passwordFrom(request.headers.get("authorization"));
  const expires = secret ? await sessionExpiry(request.headers.get("cookie"), secret) : null;
  if (pathname === "/api/admin/session") return expires ? json(200, { expires }) : json(401, { detail: "Not signed in." });
  if (secret && ((basic !== null && same(basic, secret)) || expires)) return next();

  const isPage = request.method === "GET" && !pathname.startsWith("/api/") && !pathname.startsWith("/admin/chunks/");
  if (isPage) {
    return new Response(null, {
      status: 302,
      headers: { Location: `/admin/login?next=${encodeURIComponent(pathname + search)}`, "Cache-Control": "no-store" },
    });
  }
  return json(401, { detail: "Sign in required." });
}

import { useState, type FormEvent } from "react";
import { Lock } from "lucide-react";
import { STATIC } from "@/api/client";
import { CircuitTraces, Skyline } from "@/components/SplashArt";

// The admin sign-in page (/admin/login), drawn outside the site shell over the home page's art.
// It posts the password to /api/admin/session, which frontend/middleware.ts answers with a signed
// 12-hour session cookie. Locally (ckm serve) there is no password, so it just links to /admin.

// Only same-site paths, so a crafted ?next= can't send you elsewhere after signing in.
// ("//x" and "/\x" are both read by browsers as another site.)
const safeNext = (raw: string | null) => (raw && /^\/(?![/\\])/.test(raw) ? raw : "/admin");

export default function AdminLoginPage() {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const expired = new URLSearchParams(location.search).has("expired");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/admin/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (r.ok) {
        location.href = safeNext(new URLSearchParams(location.search).get("next"));
        return;
      }
      // 401 is the gate saying the password is wrong; anything else means sign-in itself isn't working
      setError(r.status === 401 ? "That password isn't right. Try again." : "Sign-in isn't available right now. Try again in a minute.");
      setPassword("");
    } catch {
      setError("Couldn't reach the site. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="relative flex min-h-svh flex-col items-center justify-center overflow-hidden bg-background px-4 py-16 text-text">
      <CircuitTraces />
      <Skyline />
      {/* a soft wash in the middle keeps the form readable over the art */}
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgb(var(--c-background)/0.7)_0%,rgb(var(--c-background)/0.2)_50%,transparent_75%)]" />
      <a href="/" className="absolute left-5 top-5 text-[13px] text-muted hover:text-text">← arcresearch.markets</a>

      <div className="relative w-full max-w-[380px] rounded-[20px] border border-border bg-surface/90 px-7 py-8 shadow-2xl backdrop-blur-md">
        <img src="/arc-logo.png" alt="ARC Research" className="logo-img splash-logo mx-auto mb-4 h-20 w-auto" />
        <div className="text-center text-[11px] font-bold uppercase tracking-[0.12em] text-accent">ARC Research</div>
        <h1 className="mt-1.5 text-center font-serif text-2xl font-semibold">
          {expired ? "Please sign in again" : "Admin sign-in"}
        </h1>
        <p className="mb-6 mt-1 text-center text-[13px] text-muted">
          {expired ? "Your 12-hour admin session ended." : "Private tools for the research desk."}
        </p>

        {STATIC ? (
          <form onSubmit={submit} noValidate>
            <label htmlFor="admin-password" className="text-xs font-semibold text-text-2">Password</label>
            <div className="relative mt-1.5">
              <input
                id="admin-password"
                type={show ? "text" : "password"}
                autoComplete="current-password"
                autoFocus
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(null); }}
                placeholder="Enter the admin password"
                aria-invalid={!!error}
                aria-describedby="admin-error"
                className={`h-11 w-full rounded-xl border bg-surface px-3.5 pr-16 text-[15px] outline-none focus:ring-[3px] ${
                  error ? "border-danger focus:ring-danger/20" : "border-border focus:border-accent focus:ring-accent/20"
                }`}
              />
              <button type="button" onClick={() => setShow((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[13px] text-muted hover:text-text">
                {show ? "Hide" : "Show"}
              </button>
            </div>
            <p id="admin-error" role="alert" className="mb-2 mt-1.5 min-h-[18px] text-[12.5px] text-danger">{error}</p>
            <button type="submit" disabled={busy || !password}
              className="h-11 w-full rounded-xl bg-accent text-[15px] font-semibold text-on-accent hover:bg-accent-hover disabled:opacity-60">
              {busy ? "Signing in…" : "Sign in"}
            </button>
            <p className="mt-4 flex items-center justify-center gap-1.5 text-[11.5px] text-muted">
              <Lock className="h-3 w-3" /> Sessions last 12 hours on this device
            </p>
          </form>
        ) : (
          <div className="text-center">
            <p className="mb-4 text-sm text-text-2">You're running locally, so the admin needs no sign-in.</p>
            <a href="/admin" className="inline-flex h-11 w-full items-center justify-center rounded-xl bg-accent font-semibold text-on-accent hover:bg-accent-hover">
              Open the admin
            </a>
          </div>
        )}
      </div>
      <p className="relative mt-5 text-xs text-muted">
        Not an admin? <a href="/" className="underline hover:text-text">Read the research →</a>
      </p>
    </main>
  );
}

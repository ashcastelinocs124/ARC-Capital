import { useEffect, useState, type ComponentType } from "react";
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { cn } from "@/lib/cn";
import { STATIC } from "@/api/client";
import AgentsPage from "@/pages/AgentsPage";
import DailyDesk from "@/components/admin/DailyDesk";
import XPosts from "@/components/admin/XPosts";
import TradeLab from "@/components/admin/trade/TradeLab";
import { Article, DOCS_LIST, type DocDetail } from "@/pages/DocsPage";
import { PageIntro } from "@/components/layout/PageIntro";

// PRIVATE area. The data (/api/admin/*) and the detailed docs module (/admin/chunks/*) are password-gated
// by frontend/middleware.ts on the public site; locally the backend serves them without a login.
// This page's own code holds no private data, so it can safely ship in the public bundle.
const TABS = ["Agents", "Models", "Docs", "Daily desk", "X posts", "Trade Lab"] as const;

const LoadFailed = ({ what }: { what: string }) => (
  <div className="rounded-xl border border-danger bg-danger-soft px-5 py-3 text-sm">
    Couldn't load the private {what}. If you are on the public site, reload and sign in with the admin password.
  </div>
);

// The models are admin-only (since 2026-10-15): the page is a private chunk (/admin/chunks/*) and its
// data comes from /api/admin/*, so neither ships to visitors.
function AdminModels() {
  const [Page, setPage] = useState<ComponentType | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    import("@/admin/private/ModelsPage").then((m) => setPage(() => m.default), () => setFailed(true));
  }, []);
  if (failed) return <div className="mx-4 md:mx-8"><LoadFailed what="models" /></div>;
  return Page ? <Page /> : <p className="mx-4 text-sm text-muted md:mx-8">Loading…</p>;
}

function AdminDocs() {
  const [detail, setDetail] = useState<Record<string, DocDetail> | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    import("@/admin/private/docsDetail").then((m) => setDetail(m.DETAIL), () => setFailed(true));
  }, []);
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker="Admin · Docs" title="Every model in full: target, inputs, method, testing"
        steps={["What it predicts", "Target in detail", "Inputs", "Method", "Testing", "Limitations"]}
        when={{ label: `${DOCS_LIST.length} models`, value: "documented" }}>
        The public guide plus the detailed write-ups that stay private.
      </PageIntro>
      {failed && <LoadFailed what="write-ups" />}
      <div className="space-y-5">
        {DOCS_LIST.map((d) => <Article key={d.id} d={d} detail={detail?.[d.id]} />)}
      </div>
    </div>
  );
}

// Public site only: the session's end time (from the middleware) and Sign out.
function Session() {
  const [until, setUntil] = useState<string | null>(null);
  useEffect(() => {
    if (!STATIC) return;
    fetch("/api/admin/session")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j?.expires && setUntil(new Date(j.expires * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })))
      .catch(() => {});
  }, []);
  if (!STATIC) return null;
  const signOut = () =>
    fetch("/api/admin/logout", { method: "POST" }).finally(() => { location.href = "/admin/login"; });
  return (
    <>
      {until && <span className="text-danger/80">Signed in until {until}</span>}
      <button onClick={signOut} className="rounded-full border border-danger/40 px-3 py-1 text-xs font-semibold hover:bg-danger/10">
        Sign out
      </button>
    </>
  );
}

export default function AdminPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Agents");
  return (
    <div className="space-y-5 pt-4 md:pt-6">
      <div className="mx-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl md:mx-8 border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
        <span className="inline-flex items-center gap-2">
          <Lock className="h-4 w-4" />
          Private. This page and its data sit behind the admin password and are never part of the public files.
        </span>
        <span className="inline-flex flex-wrap items-center gap-3">
          <Session />
          <Link to="/" className="font-semibold underline">Back to the site</Link>
        </span>
      </div>
      <div className="mx-4 flex gap-2 md:mx-8">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={cn("rounded-full border px-4 py-1.5 text-sm font-medium",
              t === tab ? "border-accent/40 bg-accent-soft font-semibold text-accent" : "border-border bg-surface text-text-2 hover:text-accent")}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Agents" ? <AgentsPage /> : tab === "Models" ? <AdminModels /> : tab === "Docs" ? <AdminDocs /> : tab === "Daily desk" ? <DailyDesk /> : tab === "Trade Lab" ? <TradeLab /> : <XPosts />}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { cn } from "@/lib/cn";
import AgentsPage from "@/pages/AgentsPage";
import DailyDesk from "@/components/admin/DailyDesk";
import { Article, DOCS_LIST, type DocDetail } from "@/pages/DocsPage";
import { PageIntro } from "@/components/layout/PageIntro";

// PRIVATE area. The data (/api/admin/*) and the detailed docs module (/admin/chunks/*) are password-gated
// by frontend/middleware.ts on the public site; locally the backend serves them without a login.
// This page's own code holds no private data, so it can safely ship in the public bundle.
const TABS = ["Agents", "Docs", "Daily desk"] as const;

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
      {failed && (
        <div className="rounded-xl border border-danger bg-danger-soft px-5 py-3 text-sm">
          Couldn't load the private write-ups. If you are on the public site, reload and sign in with the admin password.
        </div>
      )}
      <div className="space-y-5">
        {DOCS_LIST.map((d) => <Article key={d.id} d={d} detail={detail?.[d.id]} />)}
      </div>
    </div>
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
        <Link to="/models" className="font-semibold underline">Back to the site</Link>
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
      {tab === "Agents" ? <AgentsPage admin /> : tab === "Docs" ? <AdminDocs /> : <DailyDesk />}
    </div>
  );
}

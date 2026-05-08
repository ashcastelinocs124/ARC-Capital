import { useState } from "react";
import { AlertTriangle, Lightbulb } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CounterPill, FilterPills, type FilterPill } from "@/components/ui/filter-pills";
import {
  useAgentBear,
  useAgentBull,
  useAgentCurator,
  useAgentExpressions,
  useAgentGuard,
  useAgentHypotheses,
  useAgentResearch,
  useAgentSummary,
  useAgentTriggers,
  useAgentVerdicts,
  useAgentWarnings,
  useAgentWorldState,
} from "@/hooks/useAgents";

// Pipeline stages (top-level pill row) — group agents by where they sit in the DAG
const STAGES: FilterPill[] = [
  { id: "all", label: "All Stages" },
  { id: "input", label: "Input" },
  { id: "thesis", label: "Thesis" },
  { id: "research", label: "Research" },
  { id: "debate", label: "Debate" },
  { id: "control", label: "Control" },
  { id: "memory", label: "Memory" },
];

const STAGE_AGENTS: Record<string, string[]> = {
  all: ["Trigger", "Current Event", "Hypothesis", "Asset Selection", "Research Desk", "Bull", "Bear", "Debate", "Guard", "Curator"],
  input: ["Trigger", "Current Event"],
  thesis: ["Hypothesis", "Asset Selection"],
  research: ["Research Desk"],
  debate: ["Bull", "Bear", "Debate"],
  control: ["Guard"],
  memory: ["Curator"],
};

export default function AgentsPage() {
  const [stage, setStage] = useState("all");
  const [agent, setAgent] = useState("Hypothesis");
  const { data: summary = [] } = useAgentSummary();

  const summaryByAgent = Object.fromEntries(summary.map((s) => [s.agent, s.count]));
  const totalEntries = summary.reduce((s, a) => s + a.count, 0);

  const visibleAgents = STAGE_AGENTS[stage];
  const agentPills: FilterPill[] = visibleAgents.map((a) => ({
    id: a,
    label: a,
    count: summaryByAgent[a] ?? 0,
  }));

  // Make sure the selected agent is visible in the current stage filter
  const currentAgent = visibleAgents.includes(agent) ? agent : visibleAgents[0];

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      {/* Hero counter strip */}
      <div className="flex items-center gap-2 flex-wrap">
        <h2 className="text-base font-semibold text-text mr-3">Agent Pipeline</h2>
        <CounterPill label="Total Entries" count={totalEntries} accent="default" />
        <CounterPill label="Hypotheses" count={summaryByAgent["Hypothesis"] ?? 0} accent="success" />
        <CounterPill label="Verdicts" count={summaryByAgent["Debate"] ?? 0} accent="warning" />
        <CounterPill label="Guard Decisions" count={summaryByAgent["Guard"] ?? 0} accent="danger" />
        <CounterPill label="Lessons" count={summaryByAgent["Curator"] ?? 0} accent="default" />
      </div>

      {/* Stage filter — top-level pills */}
      <div className="space-y-3">
        <FilterPills pills={STAGES} active={stage} onChange={setStage} size="lg" />

        {/* Agent sub-pills (smaller) */}
        <FilterPills
          pills={agentPills}
          active={currentAgent}
          onChange={setAgent}
          size="sm"
        />
      </div>

      {/* Selected agent's output feed */}
      <AgentFeed agent={currentAgent} />
    </div>
  );
}

function AgentFeed({ agent }: { agent: string }) {
  switch (agent) {
    case "Trigger": return <TriggersFeed />;
    case "Current Event": return <WorldStateFeed />;
    case "Hypothesis": return <HypothesesFeed />;
    case "Asset Selection": return <ExpressionsFeed />;
    case "Research Desk": return <ResearchFeed />;
    case "Bull": return <DebateFeed kind="bull" />;
    case "Bear": return <DebateFeed kind="bear" />;
    case "Debate": return <VerdictsFeed />;
    case "Guard": return <GuardFeed />;
    case "Curator": return <CuratorFeed />;
    default: return null;
  }
}

// ── Individual feeds ───────────────────────────────────────────────────

function TriggersFeed() {
  const { data = [] } = useAgentTriggers();
  return (
    <FeedCard title="Trigger Records" count={data.length}>
      {data.map((t, i) => (
        <Row key={i} timestamp={t.timestamp}>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <Badge variant="info">{t.source}</Badge>
            <Badge variant="muted">sig {t.significance.toFixed(2)}</Badge>
            <span className="text-xs text-muted-2">{t.asset_classes}</span>
          </div>
          <div className="text-sm font-medium text-text">{t.headline}</div>
          <div className="text-xs text-muted mt-0.5">{t.reason}</div>
        </Row>
      ))}
    </FeedCard>
  );
}

function WorldStateFeed() {
  const { data = [] } = useAgentWorldState();
  return (
    <FeedCard title="World State Briefs" count={data.length}>
      {data.map((w, i) => (
        <Row key={i} timestamp={w.timestamp}>
          <div className="flex items-center gap-2 mb-1.5 text-xs">
            <span className="text-muted">{w.headline_count} headlines</span>
            <span className="text-muted-2">·</span>
            <span className="text-muted">{w.indicator_reads} indicators</span>
            <span className="text-muted-2">·</span>
            <span className="text-muted">{w.surprises} surprises</span>
          </div>
          <div className="text-sm text-text leading-relaxed">{w.summary}</div>
        </Row>
      ))}
    </FeedCard>
  );
}

function HypothesesFeed() {
  const { data = [] } = useAgentHypotheses();
  return (
    <FeedCard title="Hypotheses" count={data.length}>
      {data.map((h, i) => (
        <Row key={i} timestamp={h.timestamp}>
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <Badge variant="default">{h.regime}</Badge>
            <Badge variant={h.conviction === "high" ? "success" : h.conviction === "low" ? "warning" : "muted"}>
              {h.conviction}
            </Badge>
            <Badge variant="muted">{h.horizon_days}d</Badge>
            <Badge variant="muted">{h.kill_criteria_count} kill criteria</Badge>
          </div>
          <div className="text-sm font-medium text-text mb-1 leading-relaxed">{h.thesis}</div>
          <div className="text-xs text-muted leading-relaxed">{h.rationale}</div>
        </Row>
      ))}
    </FeedCard>
  );
}

function ExpressionsFeed() {
  const { data = [] } = useAgentExpressions();
  return (
    <FeedCard title="Trade Expressions" count={data.length}>
      {data.map((e, i) => (
        <Row key={i} timestamp={e.timestamp}>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <Badge variant={e.direction === "long" ? "success" : "danger"}>{e.direction.toUpperCase()}</Badge>
            <span className="font-mono font-semibold text-sm">{e.instrument}</span>
            <span className="text-xs text-muted">size={(e.target_pct_nav * 100).toFixed(2)}% NAV</span>
            <span className="text-xs text-muted">stop={(e.stop_pct * 100).toFixed(1)}%</span>
          </div>
          <div className="text-sm text-muted leading-relaxed">{e.rationale}</div>
        </Row>
      ))}
    </FeedCard>
  );
}

function ResearchFeed() {
  const { data = [] } = useAgentResearch();
  return (
    <FeedCard title="Research Bundles" count={data.length}>
      {data.map((r, i) => (
        <Row key={i} timestamp={r.timestamp}>
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <span className="font-mono font-semibold text-sm">{r.instrument}</span>
            <Badge variant={r.sentiment === "positive" ? "success" : r.sentiment === "negative" ? "danger" : "muted"}>
              {r.sentiment}
            </Badge>
            <Badge variant="muted">{r.trend}</Badge>
            <span className="text-xs text-muted">RSI {r.rsi_14}</span>
            <span className="text-xs text-muted">vol {(r.vol_60d * 100).toFixed(1)}%</span>
            <span className="text-xs text-muted">hit {(r.hit_rate * 100).toFixed(0)}% (n={r.samples})</span>
          </div>
          <div className="text-sm text-muted leading-relaxed">{r.summary}</div>
        </Row>
      ))}
    </FeedCard>
  );
}

function DebateFeed({ kind }: { kind: "bull" | "bear" }) {
  const bull = useAgentBull();
  const bear = useAgentBear();
  const { data = [] } = kind === "bull" ? bull : bear;
  return (
    <FeedCard title={`${kind === "bull" ? "Bull" : "Bear"} Cases`} count={data.length}>
      {data.map((c, i) => (
        <Row key={i} timestamp={c.timestamp}>
          <div className="flex items-center gap-2 mb-1.5">
            <Badge variant={c.confidence === "high" ? "success" : c.confidence === "low" ? "warning" : "muted"}>
              {c.confidence}
            </Badge>
            <Badge variant="muted">{c.argument_count} args</Badge>
          </div>
          <div className="text-xs uppercase tracking-wider text-muted mb-1">Strongest argument</div>
          <div className="text-sm text-text leading-relaxed">{c.strongest}</div>
        </Row>
      ))}
    </FeedCard>
  );
}

function VerdictsFeed() {
  const { data = [] } = useAgentVerdicts();
  return (
    <FeedCard title="Debate Verdicts" count={data.length}>
      {data.map((v, i) => (
        <Row key={i} timestamp={v.timestamp}>
          <div className="flex items-center gap-2 mb-1.5">
            <Badge variant={v.decision === "proceed" ? "success" : v.decision === "reject" ? "danger" : "warning"}>
              {v.decision}
            </Badge>
            <span className="text-xs text-muted">×{v.size_multiplier}</span>
          </div>
          <div className="text-xs uppercase tracking-wider text-muted mb-0.5">Decisive factor</div>
          <div className="text-sm text-text leading-relaxed mb-2">{v.decisive_factor}</div>
          {v.dissent !== "—" && (
            <>
              <div className="text-xs uppercase tracking-wider text-muted mb-0.5">Dissent</div>
              <div className="text-sm text-muted leading-relaxed">{v.dissent}</div>
            </>
          )}
        </Row>
      ))}
    </FeedCard>
  );
}

function GuardFeed() {
  const { data: guard = [] } = useAgentGuard();
  const { data: warnings = [] } = useAgentWarnings();
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <FeedCard title="Guard Decisions" count={guard.length}>
        {guard.map((g, i) => (
          <Row key={i} timestamp={g.timestamp}>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Badge variant={g.decision === "approved" ? "success" : g.decision === "hard_veto" ? "danger" : "warning"}>
                {g.decision}
              </Badge>
              {g.amended_size !== 1.0 && (
                <span className="text-xs text-muted">×{g.amended_size.toFixed(2)}</span>
              )}
              {g.triggered_rules !== "—" && (
                <span className="text-xs text-warning">rules: {g.triggered_rules}</span>
              )}
            </div>
            <div className="text-sm text-muted leading-relaxed">{g.rationale}</div>
          </Row>
        ))}
      </FeedCard>
      <FeedCard
        title="Principle Warnings"
        count={warnings.length}
        icon={<AlertTriangle className="h-3.5 w-3.5 text-warning" />}
      >
        {warnings.map((w, i) => (
          <Row key={i} timestamp={w.timestamp}>
            <div className="flex items-center gap-2 mb-1">
              <Badge variant={w.severity === "hard" ? "danger" : "warning"}>{w.rule_id}</Badge>
              <Badge variant="muted">{w.severity}</Badge>
            </div>
            <div className="text-sm text-muted leading-relaxed">{w.description}</div>
          </Row>
        ))}
      </FeedCard>
    </div>
  );
}

function CuratorFeed() {
  const { data = [] } = useAgentCurator();
  return (
    <FeedCard
      title="Long-term Lessons"
      count={data.length}
      icon={<Lightbulb className="h-3.5 w-3.5 text-warning" />}
    >
      {data.map((l, i) => (
        <Row key={i} timestamp={l.timestamp}>
          <div className="flex items-center gap-2 mb-1">
            <Badge variant="info">{l.category}</Badge>
          </div>
          <div className="text-sm font-semibold text-text mb-1">{l.title}</div>
          <div className="text-sm text-muted leading-relaxed mb-1.5">{l.body}</div>
          {l.statistical_backing !== "—" && (
            <div className="text-xs text-muted-2 italic">{l.statistical_backing}</div>
          )}
        </Row>
      ))}
    </FeedCard>
  );
}

// ── Shared ──────────────────────────────────────────────────────────────

function FeedCard({
  title,
  count,
  icon,
  children,
}: {
  title: string;
  count: number;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  const hasItems = Array.isArray(children) ? children.length > 0 : !!children;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {icon}
          <span>{title}</span>
          <Badge variant="muted">{count}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {!hasItems ? (
          <div className="px-6 py-12 text-center text-sm text-muted">No entries yet.</div>
        ) : (
          <div className="divide-y divide-border">{children}</div>
        )}
      </CardContent>
    </Card>
  );
}

function Row({ timestamp, children }: { timestamp: string; children: React.ReactNode }) {
  return (
    <div className="px-6 py-4 hover:bg-surface-2 transition-colors">
      <div className="text-xs text-muted-2 mb-1.5 font-mono">{timestamp}</div>
      {children}
    </div>
  );
}

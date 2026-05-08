import { useMemo, useState } from "react";
import { CheckCircle2, History, Inbox } from "lucide-react";
import { ApprovalCard } from "@/components/ApprovalCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CounterPill, FilterPills, type FilterPill } from "@/components/ui/filter-pills";
import { useApprovalHistory, useApprovalQueue } from "@/hooks/useApprovals";
import { fmtRelativeTime } from "@/lib/format";

export default function ApprovalCenterPage() {
  const { data: queue = [], isLoading: queueLoading } = useApprovalQueue();
  const { data: history = [] } = useApprovalHistory();

  const [gateFilter, setGateFilter] = useState("all");

  // Build filter pills from queue contents
  const pills: FilterPill[] = useMemo(() => {
    const hyp = queue.filter((q) => q.gate === "post_hypothesis").length;
    const deb = queue.filter((q) => q.gate === "post_debate").length;
    return [
      { id: "all", label: "All", count: queue.length },
      { id: "post_hypothesis", label: "Hypothesis", count: hyp },
      { id: "post_debate", label: "Debate", count: deb },
    ];
  }, [queue]);

  const filteredQueue = gateFilter === "all" ? queue : queue.filter((q) => q.gate === gateFilter);

  // Counter strip metrics
  const approvedTotal = history.filter((h) => h.status === "approved").length;
  const rejectedTotal = history.filter((h) => h.status === "rejected").length;

  return (
    <div className="p-8 space-y-6 max-w-6xl mx-auto">
      {/* Hero counter strip */}
      <div className="flex items-center gap-2 flex-wrap">
        <h2 className="text-base font-semibold text-text mr-3">Approval Center</h2>
        <CounterPill label="Pending" count={queue.length} accent={queue.length > 0 ? "warning" : "default"} />
        <CounterPill label="Approved" count={approvedTotal} accent="success" />
        <CounterPill label="Rejected" count={rejectedTotal} accent="danger" />
      </div>

      {/* Pending section */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Inbox className="h-5 w-5 text-text" />
            <h3 className="text-sm font-semibold">Pending Decisions</h3>
          </div>
        </div>

        {/* Filter pills — Decasonic style */}
        {queue.length > 0 && (
          <div className="mb-4">
            <FilterPills pills={pills} active={gateFilter} onChange={setGateFilter} size="lg" />
          </div>
        )}

        {queueLoading ? (
          <Card>
            <CardContent className="py-12 text-center text-muted text-sm">
              Loading pending items...
            </CardContent>
          </Card>
        ) : queue.length === 0 ? (
          <Card>
            <CardContent className="py-16 text-center">
              <CheckCircle2 className="h-10 w-10 text-success mx-auto mb-3" />
              <div className="text-sm font-semibold">No pending approvals</div>
              <div className="text-xs text-muted mt-1">
                Pipeline isn't currently blocked. New items appear here automatically.
              </div>
            </CardContent>
          </Card>
        ) : filteredQueue.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted text-sm">
              No items in this category. Try a different filter.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {filteredQueue.map((item) => (
              <ApprovalCard key={item.entry_id} item={item} />
            ))}
          </div>
        )}
      </section>

      {/* History */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <History className="h-5 w-5 text-muted" />
          <h3 className="text-sm font-semibold">Recent Decisions</h3>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Decision History · last {history.length}</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {history.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-muted">
                No decisions logged yet.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {history.map((h) => (
                  <div key={h.entry_id} className="px-5 py-3 flex items-center gap-3 hover:bg-surface-2">
                    <Badge variant={h.status === "approved" ? "success" : "danger"}>
                      {h.status}
                    </Badge>
                    <span className="font-mono text-xs text-muted-2">{h.entry_id}</span>
                    <span className="text-xs text-muted">
                      {h.gate.replace("post_", "")}
                    </span>
                    <span className="flex-1 text-sm truncate text-muted">
                      {h.notes || h.rejection_reason || "—"}
                    </span>
                    <span className="text-xs text-muted-2 shrink-0">
                      {fmtRelativeTime(h.resolved_at)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

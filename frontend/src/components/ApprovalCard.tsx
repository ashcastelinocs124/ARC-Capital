import { useState } from "react";
import { Check, X, Clock } from "lucide-react";
import type { ApprovalQueueItem, HypothesisPayload, VerdictPayload } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useApproveMutation, useRejectMutation } from "@/hooks/useApprovals";
import { fmtRelativeTime } from "@/lib/format";
import { cn } from "@/lib/cn";

export function ApprovalCard({ item }: { item: ApprovalQueueItem }) {
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const approve = useApproveMutation();
  const reject = useRejectMutation();
  const busy = approve.isPending || reject.isPending;

  function onApprove() {
    setError(null);
    approve.mutate(
      { entryId: item.entry_id, notes },
      { onError: (e) => setError(e instanceof Error ? e.message : "approve failed") },
    );
  }

  function onReject() {
    if (!notes.trim()) {
      setError("Rejection requires a reason in the notes field.");
      return;
    }
    setError(null);
    reject.mutate(
      { entryId: item.entry_id, notes },
      { onError: (e) => setError(e instanceof Error ? e.message : "reject failed") },
    );
  }

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-surface-2">
          <div className="flex items-center gap-3">
            <Badge variant={item.gate === "post_hypothesis" ? "default" : "warning"}>
              {item.gate.replace("post_", "").toUpperCase()}
            </Badge>
            <span className="font-mono text-xs text-muted">{item.entry_id}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted">
            <Clock className="h-3 w-3" />
            <span>{fmtRelativeTime(item.submitted_at)}</span>
          </div>
        </div>

        {/* Payload — full context */}
        <div className="px-5 py-4 space-y-3">
          <PayloadDisplay item={item} />
        </div>

        {/* Notes input */}
        <div className="px-5 pb-3">
          <label className="text-xs uppercase tracking-wide text-muted block mb-1.5">
            Reasoning notes <span className="text-muted-2 normal-case">(required for reject)</span>
          </label>
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Why are you approving or rejecting this?"
            rows={2}
            disabled={busy}
          />
        </div>

        {/* Actions */}
        <div className="flex gap-2 px-5 pb-4">
          <Button variant="success" onClick={onApprove} disabled={busy} className="flex-1">
            <Check className="h-4 w-4" />
            Approve
          </Button>
          <Button variant="danger" onClick={onReject} disabled={busy} className="flex-1">
            <X className="h-4 w-4" />
            Reject
          </Button>
        </div>

        {/* Result message */}
        {error && (
          <div className="mx-5 mb-4 px-3 py-2 rounded-md bg-danger/10 border border-danger/30 text-danger text-xs">
            {error}
          </div>
        )}
        {(approve.isSuccess || reject.isSuccess) && (
          <div
            className={cn(
              "mx-5 mb-4 px-3 py-2 rounded-md text-xs",
              approve.isSuccess
                ? "bg-success/10 border border-success/30 text-success"
                : "bg-danger/10 border border-danger/30 text-danger",
            )}
          >
            {approve.isSuccess ? "✅ Approved" : "❌ Rejected"} · refreshing in a moment...
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PayloadDisplay({ item }: { item: ApprovalQueueItem }) {
  const payload = item.payload || {};

  if (item.gate === "post_hypothesis") {
    const p = payload as unknown as HypothesisPayload;
    return (
      <>
        <Field label="Thesis">
          <div className="text-sm leading-relaxed">{p.thesis || "—"}</div>
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Regime">
            <Badge variant="muted">{p.regime || "—"}</Badge>
          </Field>
          <Field label="Conviction">
            <Badge variant={p.conviction === "high" ? "success" : p.conviction === "low" ? "warning" : "default"}>
              {p.conviction || "—"}
            </Badge>
          </Field>
          <Field label="Horizon">
            <span className="font-mono num text-sm">{p.horizon_days || "?"}d</span>
          </Field>
        </div>
        {p.kill_criteria?.length > 0 && (
          <Field label="Kill criteria">
            <ul className="text-sm space-y-1">
              {p.kill_criteria.map((kc, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-muted-2">{i + 1}.</span>
                  <span>{kc}</span>
                </li>
              ))}
            </ul>
          </Field>
        )}
      </>
    );
  }

  if (item.gate === "post_debate") {
    const p = payload as unknown as VerdictPayload;
    return (
      <>
        <div className="flex items-center gap-3">
          <Badge variant={p.direction === "long" ? "success" : "danger"}>
            {p.direction?.toUpperCase()}
          </Badge>
          <span className="font-mono text-base font-semibold">{p.instrument}</span>
          <Badge variant={p.decision === "proceed" ? "success" : p.decision === "reject" ? "danger" : "warning"}>
            {p.decision}
          </Badge>
          <span className="text-xs text-muted">×{p.size_multiplier}</span>
        </div>
        <Field label="Decisive factor">
          <div className="text-sm leading-relaxed">{p.decisive_factor || "—"}</div>
        </Field>
        {p.dissent && (
          <Field label="Dissent">
            <div className="text-sm leading-relaxed text-muted">{p.dissent}</div>
          </Field>
        )}
      </>
    );
  }

  return (
    <pre className="text-xs text-muted bg-surface-2 p-3 rounded-md overflow-auto">
      {JSON.stringify(payload, null, 2)}
    </pre>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted mb-1">{label}</div>
      {children}
    </div>
  );
}

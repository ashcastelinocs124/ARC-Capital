import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { btn, Segmented } from "@/components/admin/shell";
import { BASE, call, type Detail, type Exhibit, type HandEdit, type Note, type NoteItem } from "@/components/admin/deskApi";

// The Daily desk's Editor tab, left side: the day's note as its Substack post reads (substack.build_doc), on a light
// page in both themes (.paper in index.css). Three modes: view; diff (a draft from the Editor marked in place, red =
// removed, green = added); edit (type, bold, move charts, then Save). Charts sit where substack.chart_slots puts them.

const PARAS = /\n\s*\n/;
const paras = (body: string) => body.split(PARAS).map((p) => p.trim()).filter(Boolean);
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const html = (md: string) => ({ __html: esc(md).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>") });

// Back to the note's markdown: bold (<b>, <strong>, a bold style) becomes **…**, every other tag is dropped.
function toMd(node: Node): string {
  let out = "";
  node.childNodes.forEach((c) => {
    if (c.nodeType === Node.TEXT_NODE) out += c.textContent ?? "";
    else if (c instanceof HTMLElement) {
      const bold = c.tagName === "B" || c.tagName === "STRONG" || /bold|[6-9]00/.test(c.style.fontWeight);
      out += c.tagName === "BR" ? " " : bold ? `**${toMd(c)}**` : toMd(c);
    }
  });
  return out;
}
const md = (el: Element | null) =>
  el ? toMd(el).replace(/\*\*\*\*/g, "").replace(/\*\*(\s*)\*\*/g, "$1").replace(/ /g, " ").replace(/\s+/g, " ").trim() : "";

type Place = { at: number; after: number | null };
const hostOf = (e: Exhibit, note: Note) =>
  e.at ?? e.item ?? note.items.find((it) => it.chart && it.chart === e.finding_id)?.rank ?? 0;

/** The charts item `rank` shows, keyed by the paragraph they follow (0 = under the heading). */
function slots(rank: number, n: number, exhibits: Exhibit[], place: (e: Exhibit) => Place) {
  const out = new Map<number, Exhibit[]>();
  for (const e of [...exhibits].sort((a, b) => a.n - b.n)) {
    const p = place(e);
    if (p.at !== rank) continue;
    const k = p.after == null ? n : Math.min(p.after, n);
    out.set(k, [...(out.get(k) ?? []), e]);
  }
  return out;
}

export type PreviewHandle = { collect(): HandEdit; firstChange(): void };

type Props = {
  day: string;
  note: Note;
  exhibits: Exhibit[];
  calendar: string[];
  src: (file: string) => string;
  mode: "view" | "diff" | "edit";
  base?: { note: Note; exhibits: Exhibit[]; src: (file: string) => string }; // diff: the note as it is now
};

export const NotePreview = forwardRef<PreviewHandle, Props>(function NotePreview(
  { day, note, exhibits, calendar, src, mode, base }, ref,
) {
  const art = useRef<HTMLElement>(null);
  const editing = mode === "edit";
  const initial = useMemo(
    () => Object.fromEntries(exhibits.map((e) => [e.file, { at: hostOf(e, note), after: e.after ?? null }])) as Record<string, Place>,
    [exhibits, note],
  );
  const [places, setPlaces] = useState(initial); // NotePane remounts this on a new note or a discard
  const [drop, setDrop] = useState<string | null>(null);
  const dragged = useRef<string | null>(null);
  const place = (e: Exhibit): Place => (editing ? places[e.file] : null) ?? { at: hostOf(e, note), after: e.after ?? null };

  // every place a chart can go, in reading order: under each heading, then after each paragraph
  const order = note.items.slice().sort((a, b) => a.rank - b.rank)
    .flatMap((it) => Array.from({ length: paras(it.body).length + 1 }, (_, i) => `${it.rank}:${i}`));
  const step = (file: string, by: -1 | 1) => {
    const p = places[file];
    const n = paras(note.items.find((it) => it.rank === p.at)?.body ?? "").length;
    const i = order.indexOf(`${p.at}:${p.after ?? n}`) + by;
    if (i < 0 || i >= order.length) return;
    const [at, after] = order[i].split(":").map(Number);
    setPlaces({ ...places, [file]: { at, after } });
  };

  useImperativeHandle(ref, () => ({
    collect() {
      const q = (k: string) => art.current?.querySelector(`[data-ed="${k}"]`) ?? null;
      return {
        headline: md(q("h")),
        takeaways: note.takeaways.map((_, i) => md(q(`tk:${i}`))),
        items: note.items.map((it) => ({
          rank: it.rank,
          title: md(q(`t:${it.rank}`)),
          body: paras(it.body).map((_, i) => md(q(`p:${it.rank}:${i}`))).join("\n\n"),
          view: it.view ? md(q(`v:${it.rank}`)) : null,
        })),
        charts: Object.entries(places).map(([file, p]) => ({ file, at: p.at, after: p.after })),
      };
    },
    firstChange() {
      const c = art.current?.querySelector(".add, .del");
      c?.scrollIntoView({ block: "start", behavior: "smooth" });
    },
  }));

  const ed = (key: string) =>
    editing
      ? {
          "data-ed": key,
          contentEditable: true,
          suppressContentEditableWarning: true,
          onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter") e.preventDefault(); }, // one block, no new paragraphs
          onPaste: (e: React.ClipboardEvent) => { e.preventDefault(); document.execCommand("insertText", false, e.clipboardData.getData("text/plain")); },
        }
      : { "data-ed": key };

  const figure = (e: Exhibit, from: (f: string) => string = src) => (
    <figure key={`f-${e.file}`} className={cn("my-5", editing && "moving")} draggable={editing}
      onDragStart={(ev) => { dragged.current = e.file; ev.dataTransfer.effectAllowed = "move"; }}
      onDragEnd={() => { dragged.current = null; setDrop(null); }}>
      {editing && (
        <div className="mb-1.5 flex cursor-grab select-none items-center gap-1.5 rounded-md border border-[rgb(var(--p-line))] bg-[rgb(var(--p-line)/0.4)] px-2 py-1 font-sans text-xs text-[rgb(var(--p-muted))]">
          <span aria-hidden="true">⠿</span>
          <span className="flex-1">Drag to move {e.title.split(":")[0]}</span>
          {([-1, 1] as const).map((d) => (
            <button key={d} type="button" onClick={() => step(e.file, d)} aria-label={`Move ${e.title.split(":")[0]} ${d < 0 ? "up" : "down"}`}
              className="rounded border border-[rgb(var(--p-line))] bg-[rgb(var(--p-bg))] px-2 text-[13px] text-[rgb(var(--p-ink))] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[rgb(var(--p-brand))]">
              {d < 0 ? "↑" : "↓"}
            </button>
          ))}
        </div>
      )}
      <img src={from(e.file)} alt={e.title} className="block w-full" />
      <figcaption className="mt-1.5 text-center font-sans text-[13px] text-[rgb(var(--p-muted))]">{e.title}</figcaption>
    </figure>
  );

  const view = (it: NoteItem) =>
    it.view ? (
      <blockquote key={`v-${it.rank}`}>
        <p><strong>ARC view · {it.view.topic || it.view.consultant}</strong></p>
        <p {...ed(`v:${it.rank}`)} dangerouslySetInnerHTML={html(it.view.text)} />
      </blockquote>
    ) : null;

  // an item as the post shows it; `charts` from that note's exhibits, `extra` after the title
  const item = (it: NoteItem, ex: Exhibit[], from = src, extra?: React.ReactNode, keyed = "") => {
    const ps = paras(it.body);
    const at = slots(it.rank, ps.length, ex, (e) => (from === src ? place(e) : { at: hostOf(e, base!.note), after: e.after ?? null }));
    const out: React.ReactNode[] = [
      <h3 key={`h3-${keyed}${it.rank}`} data-slot={`${it.rank}:0`} className="mb-2.5 mt-8 text-[23px] leading-snug">
        {it.rank}. <span {...ed(`t:${it.rank}`)} dangerouslySetInnerHTML={html(it.title)} />{extra}
      </h3>,
    ];
    for (let i = 0; i <= ps.length; i++) {
      if (i) out.push(<p key={`p-${keyed}${it.rank}-${i}`} data-slot={`${it.rank}:${i}`} {...ed(`p:${it.rank}:${i - 1}`)} dangerouslySetInnerHTML={html(ps[i - 1])} />);
      if (editing && drop === `${it.rank}:${i}`) out.push(<div key="drop" className="dropline" />);
      out.push(...(at.get(i) ?? []).map((e) => figure(e, from)));
    }
    out.push(view(it));
    return out;
  };

  const kicker = new Date(`${day}T12:00:00`);
  const head = (h: React.ReactNode) => (
    <>
      {h}
      <p className="mb-5 font-sans text-[19px] leading-snug text-[rgb(var(--p-muted))]">
        ARC Daily Update · {kicker.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
      </p>
      <div className="flex items-center gap-2.5 font-sans text-[13px] text-[rgb(var(--p-muted))]">
        <span aria-hidden="true" className="grid h-[34px] w-[34px] place-items-center rounded-full bg-[rgb(var(--p-brand))] text-xs font-bold text-[rgb(var(--p-bg))]">AC</span>
        <span><b className="block text-[rgb(var(--p-ink))]">Ashleyn Castelino</b>{kicker.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
      </div>
      <hr className="my-5 border-[rgb(var(--p-line))]" />
    </>
  );
  const title = (h: string, edKey?: string) => (
    <h2 {...(edKey ? ed(edKey) : {})} className="mb-2 text-[32px] leading-tight tracking-tight" dangerouslySetInnerHTML={html(h)} />
  );
  const tail = (
    <>
      {calendar.length > 0 && (
        <>
          <h3 className="mb-2.5 mt-8 text-[23px]">Other news on the calendar today</h3>
          <ul className="mb-4 list-disc pl-6">{calendar.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </>
      )}
      <p className="text-base text-[rgb(var(--p-muted))]">Not investment advice.</p>
    </>
  );

  let body: React.ReactNode;
  if (mode === "diff" && base) {
    const was = new Map(base.note.items.map((it) => [it.title, it]));
    const now = new Set(note.items.map((it) => it.title));
    const tag = (t: string) => <span className="tag">{t}</span>;
    body = (
      <>
        {head(note.headline === base.note.headline ? title(note.headline) : (
          <><div className="del">{tag("− Removed")}{title(base.note.headline)}</div><div className="add">{tag("+ Added")}{title(note.headline)}</div></>
        ))}
        <ul className="mb-5 list-disc pl-6">
          {note.takeaways.map((t, i) => t === base.note.takeaways[i] ? <li key={i} dangerouslySetInnerHTML={html(t)} /> : (
            <li key={i} className="list-none">
              <div className="del">{tag("− Removed")}<p className="!mb-1" dangerouslySetInnerHTML={html(base.note.takeaways[i] ?? "")} /></div>
              <div className="add">{tag("+ Added")}<p className="!mb-1" dangerouslySetInnerHTML={html(t)} /></div>
            </li>
          ))}
        </ul>
        {note.items.slice().sort((a, b) => a.rank - b.rank).flatMap((it) => {
          const o = was.get(it.title);
          const gone = base.note.items.filter((x) => !now.has(x.title) && x.rank === it.rank);
          const out: React.ReactNode[] = [];
          if (!o) out.push(<div key={`add-${it.rank}`} className="add">{tag(`+ Added · new item ${it.rank}`)}{item(it, exhibits)}</div>);
          else if (o.body !== it.body) {
            out.push(<h3 key={`h3c-${it.rank}`} className="mb-2.5 mt-8 text-[23px]">{it.rank}. <span dangerouslySetInnerHTML={html(it.title)} /></h3>);
            out.push(<div key={`del-${it.rank}`} className="del">{tag("− Removed")}{paras(o.body).map((p, i) => <p key={i} dangerouslySetInnerHTML={html(p)} />)}</div>);
            out.push(<div key={`addb-${it.rank}`} className="add">{tag("+ Added")}{paras(it.body).map((p, i) => <p key={i} dangerouslySetInnerHTML={html(p)} />)}</div>);
            const own = slots(it.rank, 0, exhibits, place);
            out.push(...[...own.values()].flat().map((e) => figure(e)), view(it));
          } else {
            const moved = o.rank !== it.rank ? <span className="ml-2 align-middle font-sans text-[11px] font-semibold text-[rgb(var(--p-muted))]">unchanged · was {o.rank}</span> : undefined;
            out.push(...item(it, exhibits, src, moved));
          }
          for (const g of gone) {
            out.push(<div key={`gone-${g.rank}`} className="del">{tag(`− Removed · was item ${g.rank}`)}{item(g, base.exhibits, base.src, undefined, "old-")}</div>);
          }
          return out;
        })}
        {tail}
      </>
    );
  } else {
    body = (
      <>
        {head(title(note.headline, "h"))}
        <ul className="mb-5 list-disc pl-6">{note.takeaways.map((t, i) => <li key={i} {...ed(`tk:${i}`)} dangerouslySetInnerHTML={html(t)} />)}</ul>
        {note.items.slice().sort((a, b) => a.rank - b.rank).flatMap((it) => item(it, exhibits))}
        {tail}
      </>
    );
  }

  return (
    <article ref={art} className="post mx-auto max-w-[660px] px-6 pb-12 pt-7"
      onDragOver={(ev) => {
        if (!dragged.current) return;
        ev.preventDefault();
        const above = [...(art.current?.querySelectorAll<HTMLElement>("[data-slot]") ?? [])]
          .filter((el) => el.getBoundingClientRect().bottom <= ev.clientY + 20).pop();
        setDrop(above?.dataset.slot ?? null);
      }}
      onDrop={(ev) => {
        ev.preventDefault();
        const file = dragged.current;
        if (file && drop) {
          const [at, after] = drop.split(":").map(Number);
          setPlaces({ ...places, [file]: { at, after } });
        }
        setDrop(null);
      }}>
      {body}
    </article>
  );
});

// ── the pane: the bar over the preview, and what its buttons do ────────────

type Bar = { kind: "idle"; msg?: string } | { kind: "edit" } | { kind: "warn"; warnings: string[]; edit: HandEdit } | { kind: "busy"; msg: string };

export type PaneHandle = { firstChange(): void };

export const NotePane = forwardRef<PaneHandle, {
  detail: Detail;
  onReload: () => void;
  onDecided: (approved: boolean, message: string) => void;
}>(function NotePane({ detail, onReload, onDecided }, ref) {
  const day = detail.date;
  const preview = useRef<PreviewHandle>(null);
  const [bar, setBar] = useState<Bar>({ kind: "idle" });
  const [final, setFinal] = useState(false);
  const [resetKey, setResetKey] = useState(0);
  const [err, setErr] = useState("");
  const prop = detail.proposal;
  const running = detail.job?.state === "running";
  useImperativeHandle(ref, () => ({ firstChange: () => { setFinal(false); setTimeout(() => preview.current?.firstChange(), 50); } }));

  const stamp = encodeURIComponent(detail.hand_edited_at || detail.generated_at);
  const src = (f: string) => `${BASE}/${day}/charts/${f}?v=${stamp}`;
  const propSrc = (f: string) => `${BASE}/${day}/proposal/charts/${f}?v=${encodeURIComponent(prop?.created_at ?? "")}`;
  const fail = (e: unknown) => setErr(String((e as Error).message ?? e));

  const save = (edit: HandEdit) => {
    setBar({ kind: "busy", msg: "Saving your edits…" });
    call(`/${day}/note`, { edit }).then(() => { setBar({ kind: "idle", msg: "Saved · your edits are in the note (old copy backed up) · not sent to Substack yet" }); onReload(); })
      .catch((e) => { fail(e); setBar({ kind: "edit" }); });
  };
  const trySave = () => {
    const edit = preview.current!.collect();
    setErr("");
    call<{ warnings: string[] }>(`/${day}/note/check`, { edit })
      .then((r) => (r.warnings.length ? setBar({ kind: "warn", warnings: r.warnings, edit }) : save(edit)))
      .catch(fail);
  };
  const decide = (approve: boolean) => {
    setErr("");
    call<{ message?: string }>(`/${day}/edit/${approve ? "approve" : "reject"}`, {})
      .then((r) => {
        setBar({ kind: "idle", msg: approve ? "Approved · note saved with its charts · not sent to Substack yet" : undefined });
        onDecided(approve, r.message ?? "");
        onReload();
      })
      .catch(fail);
  };

  const kind = prop ? (prop.kind === "new" ? "New point" : prop.summary.changed.length ? `Change to item ${prop.summary.changed.join(", ")}` : "Change") : "";
  let left: React.ReactNode, right: React.ReactNode = null;
  if (prop && bar.kind !== "busy") {
    left = <span><b className="text-warning">Proposed edit · {kind}</b> · {prop.summary.text}</span>;
    right = (
      <>
        <Segmented label="Preview mode" value={final ? "f" : "c"} options={[["c", "Changes"], ["f", "Final post"]]} onChange={(v) => setFinal(v === "f")} />
        <button type="button" className={btn.secondary} onClick={() => decide(false)}>Reject</button>
        <button type="button" className={btn.primary} onClick={() => decide(true)}>Approve</button>
      </>
    );
  } else if (bar.kind === "edit") {
    left = <span><b className="text-warning">Editing</b> · click any text to change it; select words and press B (or ⌘B) to bold; drag a chart or use ↑ ↓</span>;
    right = (
      <>
        <button type="button" className={cn(btn.secondary, "w-9 justify-center font-extrabold")} aria-label="Bold"
          onMouseDown={(e) => { e.preventDefault(); document.execCommand("bold"); }}>B</button>
        <button type="button" className={btn.secondary} onClick={() => { setBar({ kind: "idle" }); setResetKey((k) => k + 1); setErr(""); }}>Discard</button>
        <button type="button" className={btn.primary} onClick={trySave}>Save</button>
      </>
    );
  } else if (bar.kind === "warn") {
    const n = bar.warnings.length;
    left = <span><b className="text-warning">{n} figure{n > 1 ? "s aren't" : " isn't"} in that item's cited facts:</b> {bar.warnings.join("; ")}. Readers will see {n > 1 ? "them" : "it"} as written.</span>;
    right = (
      <>
        <button type="button" className={btn.secondary} onClick={() => setBar({ kind: "edit" })}>Keep editing</button>
        <button type="button" className={btn.primary} onClick={() => save(bar.edit)}>Save anyway</button>
      </>
    );
  } else if (bar.kind === "busy") {
    left = <span className="text-warning">{bar.msg}</span>;
  } else {
    left = <span>{bar.msg ? <b className="text-accent">{bar.msg}</b> : "Preview · how this note looks on Substack"}</span>;
    right = (
      <button type="button" className={btn.secondary} disabled={running} onClick={() => { setBar({ kind: "edit" }); setErr(""); }}
        title={running ? "Wait for the running job to finish" : "Edit the text and move charts, like the Substack editor"}>
        ✎ Edit text
      </button>
    );
  }

  return (
    <section aria-label="The note as it will look on Substack" className="overflow-hidden rounded-2xl border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface px-3 py-2 text-[12.5px] text-text-2">
        <div className="min-w-0 flex-1" aria-live="polite">{left}</div>
        {right && <div className="flex flex-wrap items-center gap-1.5">{right}</div>}
      </div>
      {err && <div role="alert" className="border-b border-danger bg-danger-soft px-3 py-2 text-sm text-danger">{err}</div>}
      <div className="paper max-h-[78vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-[rgb(var(--p-line))] px-6 py-3 font-serif text-[15px] font-semibold">
          ARC Research
          <span className="rounded-md bg-[rgb(var(--p-brand))] px-3 py-1.5 font-sans text-xs font-semibold text-[rgb(var(--p-bg))]">Subscribe</span>
        </div>
        {prop && bar.kind !== "busy" ? (
          <NotePreview key={`p-${prop.created_at}-${final}`} ref={preview} day={day} note={prop.note} exhibits={prop.exhibits} calendar={prop.calendar}
            src={propSrc} mode={final ? "view" : "diff"} base={{ note: detail.note, exhibits: detail.exhibits, src }} />
        ) : (
          <NotePreview key={`n-${detail.generated_at}-${detail.hand_edited_at}-${resetKey}`} ref={preview} day={day} note={detail.note}
            exhibits={detail.exhibits} calendar={detail.calendar} src={src} mode={bar.kind === "edit" || bar.kind === "warn" ? "edit" : "view"} />
        )}
      </div>
    </section>
  );
});

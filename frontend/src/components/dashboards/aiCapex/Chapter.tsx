import type { ReactNode } from "react";

/** "**$181bn**" -> <b>$181bn</b>: the run's code-written sentences mark their key numbers that way. */
export function Bold({ text }: { text: string }) {
  return <>{text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <b key={i} className="text-text">{part}</b> : part))}</>;
}

export function Unavailable({ what }: { what: string }) {
  return <p className="text-sm text-muted">Unavailable · {what}</p>;
}

export function SourceLink({ title, url }: { title: string; url: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="underline decoration-accent/60 underline-offset-2 hover:text-accent">
      {title}
    </a>
  );
}

/** One numbered question: the code-written answer on the left, its charts on the right. */
export function Chapter({ id, n, tag, question, sentence, note, children }: {
  id: string; n: string; tag: string; question: string; sentence?: string; note?: ReactNode; children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="bg-surface border border-border rounded-xl shadow-card px-4 py-4 md:px-5 grid gap-5 md:grid-cols-[250px_1fr] scroll-mt-4">
      <div>
        <div className="font-mono text-xs text-accent">{n} · {tag}</div>
        <h2 id={`${id}-h`} className="font-serif font-bold text-[22px] leading-tight text-text mt-1 mb-2">{question}</h2>
        {sentence && <p className="text-[13.5px] leading-[21px] text-text-2 mb-2"><Bold text={sentence} /></p>}
        {note && <div className="text-xs leading-[18px] text-muted">{note}</div>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

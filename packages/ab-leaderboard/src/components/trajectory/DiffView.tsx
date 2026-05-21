import { FileText } from "lucide-react";

export type DiffLine = { kind: "add" | "del" | "ctx"; text: string };

interface DiffViewProps {
  before: DiffLine[];
  after: DiffLine[];
  beforeTitle: string;
  afterTitle: string;
}

export function DiffView({ before, after, beforeTitle, afterTitle }: DiffViewProps): JSX.Element {
  return (
    <div className="grid grid-cols-2 gap-3.5">
      <DiffPane title={beforeTitle} lines={before} hint="before · superseded" />
      <DiffPane title={afterTitle} lines={after} hint="+ created · 47 lines" hintClass="text-pass" />
    </div>
  );
}

function DiffPane({
  title,
  lines,
  hint,
  hintClass,
}: {
  title: string;
  lines: DiffLine[];
  hint: string;
  hintClass?: string;
}): JSX.Element {
  return (
    <div className="rounded-lg border border-border overflow-hidden bg-background-2 font-mono text-[11.5px]">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-panel-2 font-sans text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5"><FileText className="size-3" /> {title}</span>
        <span className={hintClass}>{hint}</span>
      </div>
      <div className="overflow-x-auto">
        {lines.map((l, i) => {
          const mark = l.kind === "add" ? "+" : l.kind === "del" ? "−" : " ";
          return (
            <div
              key={i}
              className={`flex leading-relaxed whitespace-pre ${
                l.kind === "add" ? "bg-pass/[0.07]" : l.kind === "del" ? "bg-fail/[0.07]" : ""
              }`}
            >
              <span className="w-9 text-right pr-2 text-muted-foreground text-[10.5px] select-none">{i + 1}</span>
              <span
                className={
                  "w-4 text-center " +
                  (l.kind === "add" ? "text-pass" : l.kind === "del" ? "text-fail" : "text-muted-foreground")
                }
              >
                {mark}
              </span>
              <span className="flex-1 pr-3 text-foreground-2">{l.text || " "}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

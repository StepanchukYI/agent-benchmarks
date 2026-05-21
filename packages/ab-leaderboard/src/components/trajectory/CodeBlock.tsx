import { type ReactNode } from "react";
import { FileText } from "lucide-react";
import { cn } from "../../lib/utils";

export type Token = { t: "k" | "s" | "n" | "p" | "c" | "type" | "v"; v: string };

interface CodeBlockProps {
  tokens: Token[];
  header?: ReactNode;
  lang?: string;
  className?: string;
}

const TOKEN_CLASS: Record<Token["t"], string> = {
  k:    "text-purple-300 dark:text-purple-300 text-purple-700",
  s:    "text-emerald-300 dark:text-emerald-300 text-emerald-700",
  n:    "text-amber-300 dark:text-amber-300 text-amber-700",
  p:    "text-muted-foreground",
  c:    "text-slate-400 italic",
  type: "text-cyan-300 dark:text-cyan-300 text-cyan-700",
  v:    "text-rose-300 dark:text-rose-300 text-rose-700",
};

export function CodeBlock({ tokens, header, lang = "text", className }: CodeBlockProps): JSX.Element {
  return (
    <div className={cn("rounded-lg border border-border overflow-hidden font-mono text-[11.5px] leading-relaxed bg-background-2", className)}>
      {header != null && (
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-panel-2 font-sans text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <FileText className="size-3" />
            {header}
          </span>
          <span>{lang}</span>
        </div>
      )}
      <pre className="m-0 px-3.5 py-3 overflow-x-auto text-foreground-2">
        {tokens.map((seg, i) => (
          <span key={i} className={TOKEN_CLASS[seg.t]}>{seg.v}</span>
        ))}
      </pre>
    </div>
  );
}

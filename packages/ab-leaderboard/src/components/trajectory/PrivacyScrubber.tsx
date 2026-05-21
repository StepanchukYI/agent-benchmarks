import { Eye, Github, Lock, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Panel, PanelHeader } from "../ui/Panel";
import { StatusPill } from "../ui/StatusPill";
import { Button } from "../ui/Button";
import { useSubmissionPrivacyScan } from "../../api/hooks";

/**
 * Pre-publish privacy scrubber preview (LSN-006).
 * Shows what `ab publish`'s privacy_check would catch and offers an Auto-scrub
 * action; toggles to "ready to publish" once applied.
 */
export function PrivacyScrubber(): JSX.Element {
  const [scrubbed, setScrubbed] = useState(false);
  // No submission selected in this view — the hook falls back to mock data
  // until the trajectory carries a submission_id we can scan against.
  const { data: scrubberFinds } = useSubmissionPrivacyScan("preview");
  const finds = scrubberFinds ?? [];

  return (
    <Panel>
      <PanelHeader
        title={
          <span className={"inline-flex items-center gap-1.5 " + (scrubbed ? "text-pass" : "text-warn")}>
            {scrubbed ? <ShieldCheck className="size-3" /> : <Eye className="size-3" />}
            Publish preview
          </span>
        }
        actions={
          <StatusPill kind={scrubbed ? "pass" : "warn"} size="sm">
            {scrubbed ? "ready to publish" : "needs scrubbing"}
          </StatusPill>
        }
      />
      <div className="p-3.5 flex flex-col gap-2.5">
        {!scrubbed ? (
          <>
            <div className="text-muted-foreground text-[11px]">
              {finds.length} potentially sensitive reference{finds.length === 1 ? "" : "s"} detected.
            </div>
            <ul>
              {finds.map((f, i) => (
                <li key={i} className={"flex items-start gap-2 py-2 " + (i > 0 ? "border-t border-border-soft" : "")}>
                  <span className="font-mono text-[10.5px] text-muted-foreground bg-panel-3 rounded px-1.5 py-px shrink-0">
                    L{f.line}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-medium text-foreground-2">{f.kind}</div>
                    <div className="font-mono text-[10.5px] text-warn break-all mt-0.5">{f.match}</div>
                  </div>
                </li>
              ))}
            </ul>
            <div className="flex gap-1.5 mt-1">
              <Button size="sm" variant="primary" className="flex-1 justify-center" onClick={() => setScrubbed(true)}>
                <ShieldCheck className="size-3" /> Auto-scrub
              </Button>
              <Button size="sm" className="flex-1 justify-center">
                <Lock className="size-3" /> Keep private
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-[11.5px] text-foreground-2 leading-relaxed">
              All vault paths replaced with <span className="font-mono">&lt;vault&gt;/…</span>; account references masked.
              Trajectory ready to publish via <span className="font-mono">ab publish</span>.
            </p>
            <div className="flex gap-1.5">
              <Button size="sm" variant="primary" className="flex-1 justify-center">
                <Github className="size-3" /> Publish to repo
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setScrubbed(false)} title="Show finds again">
                <Eye className="size-3" />
              </Button>
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

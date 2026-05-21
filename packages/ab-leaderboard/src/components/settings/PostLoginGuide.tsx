/**
 * "Now what?" guide shown after a successful sign-in.
 *
 * Walks the operator through: install CLI → connect repo → run + publish →
 * sync. Each step has a copyable command; the panel collapses to a single
 * "Hide guide" line once the user dismisses it (state: localStorage so it
 * doesn't reappear after refresh).
 */

import { Check, ChevronDown, ChevronRight, Copy, Rocket, Terminal } from "lucide-react";
import { useEffect, useState } from "react";

import { Panel, PanelHeader } from "../ui/Panel";

const LS_KEY = "ab.settings.post_login_guide.dismissed";

interface StepProps {
  num: number;
  title: string;
  body: React.ReactNode;
  cmd?: string;
}

function Step({ num, title, body, cmd }: StepProps): JSX.Element {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    if (!cmd) return;
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard blocked — user can still select manually
    }
  }

  return (
    <div className="flex gap-3 py-3 border-b border-border-soft last:border-b-0">
      <div className="size-6 shrink-0 grid place-items-center rounded-full bg-panel-3 text-[11.5px] font-semibold text-foreground-2">
        {num}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] font-medium">{title}</div>
        <div className="text-[11.5px] text-muted-foreground mt-0.5">{body}</div>
        {cmd && (
          <div className="mt-2 flex items-center gap-2 group">
            <pre className="flex-1 min-w-0 overflow-x-auto rounded-md border border-border bg-panel-2 px-2.5 py-1.5 text-[11.5px] font-mono text-foreground-2">
              <code>{cmd}</code>
            </pre>
            <button
              onClick={copy}
              className="size-7 grid place-items-center rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-panel-3"
              title={copied ? "copied" : "copy command"}
              aria-label="copy command"
            >
              {copied ? <Check className="size-3.5 text-pass" /> : <Copy className="size-3.5" />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function PostLoginGuide(): JSX.Element | null {
  const [dismissed, setDismissed] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(LS_KEY) === "1");
    } catch {
      // private mode / disabled storage — guide just always shows
    }
  }, []);

  function dismiss(): void {
    try {
      localStorage.setItem(LS_KEY, "1");
    } catch {
      // ignore
    }
    setDismissed(true);
  }

  if (dismissed) {
    return (
      <button
        onClick={() => setDismissed(false)}
        className="text-[11.5px] text-muted-foreground hover:text-foreground self-start"
      >
        Show onboarding guide
      </button>
    );
  }

  return (
    <Panel>
      <PanelHeader
        title={
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="inline-flex items-center gap-2 text-left"
            aria-expanded={!collapsed}
          >
            {collapsed ? <ChevronRight className="size-3.5" /> : <ChevronDown className="size-3.5" />}
            <Rocket className="size-3.5 text-accent" />
            Onboarding — 4 steps to your first leaderboard row
          </button>
        }
        actions={
          <button
            onClick={dismiss}
            className="text-[11.5px] text-muted-foreground hover:text-foreground"
          >
            Hide
          </button>
        }
      />
      {!collapsed && (
        <div className="px-4 pb-2 pt-1">
          <Step
            num={1}
            title="Install the CLI"
            body={
              <>
                Clones the monorepo and installs the <span className="font-mono">ab</span> command into your venv.
                Requires Python 3.11+ and <span className="font-mono">uv</span>.
              </>
            }
            cmd="git clone https://github.com/StepanchukYI/agent-benchmarks.git && cd agent-benchmarks && uv sync"
          />
          <Step
            num={2}
            title="Connect a results repo"
            body={
              <>
                Either click <span className="font-medium">Connected repos → Add repo</span> in the sidebar,
                or use the CLI. The repo is read-only for the server.
              </>
            }
            cmd="uv run ab register https://github.com/<you>/agent-benchmarks-runs"
          />
          <Step
            num={3}
            title="Run a benchmark"
            body={
              <>
                <span className="font-mono">ab wizard</span> walks you through runner / model / effort / suite /
                tier picks and prints the equivalent <span className="font-mono">ab run</span> invocation.
                Use a single L0 task first to validate the loop.
              </>
            }
            cmd="uv run ab wizard"
          />
          <Step
            num={4}
            title="Publish & sync"
            body={
              <>
                Push results to your repo, then trigger a sync (or wait ~30s for the auto-poller). The server
                re-scores from your trajectory; your row joins the leaderboard.
              </>
            }
            cmd="uv run ab publish && # then hit 'Sync all' in the Connected repos tab"
          />
          <div className="pt-2 text-[11px] text-muted-foreground">
            <Terminal className="inline size-3 mr-1" />
            Full walkthrough: <a className="text-accent hover:underline" href="https://github.com/StepanchukYI/agent-benchmarks/blob/main/docs/friend-onboarding.md" target="_blank" rel="noreferrer">docs/friend-onboarding.md</a>
          </div>
        </div>
      )}
    </Panel>
  );
}

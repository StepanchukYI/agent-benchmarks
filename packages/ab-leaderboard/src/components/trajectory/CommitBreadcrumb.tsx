import { ExternalLink, Github } from "lucide-react";
import { Avatar } from "../ui/Avatar";
import { TrustDot } from "../domain/TrustDot";
import { useDefaultTrajectory, useOperators } from "../../api/hooks";
import { shortSha } from "../../lib/format";

/** Provenance strip: who ran this, where it lives, which commit, run id. */
export function CommitBreadcrumb(): JSX.Element {
  const { data: trajectory } = useDefaultTrajectory();
  const { data: operators } = useOperators();
  if (!trajectory) return <></>;
  const op = (operators ?? []).find((o) => o.handle === trajectory.operator);
  if (!op) return <></>;
  return (
    <div className="flex items-center gap-2 px-6 py-1.5 bg-background-2 border-b border-border-soft text-[11px]">
      <span className="inline-flex items-center gap-1.5 text-foreground-2 font-medium">
        <Avatar operator={op} size={14} />
        @{op.handle}
      </span>
      <Sep />
      <a
        href={`https://${trajectory.source_repo}`}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 font-mono text-muted-foreground hover:text-foreground"
      >
        <Github className="size-3" />
        {trajectory.source_repo}
      </a>
      <Sep />
      <a
        href={`https://${trajectory.source_repo}/commit/${trajectory.source_commit_sha}`}
        target="_blank"
        rel="noreferrer"
        className="font-mono text-accent hover:underline"
      >
        {shortSha(trajectory.source_commit_sha)}
      </a>
      <Sep />
      <span className="font-mono text-foreground-2">{trajectory.run_id}</span>
      <span className="flex-1" />
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <TrustDot tier={trajectory.trust_tier} size={11} commit={trajectory.source_commit_sha} />
        official
      </span>
      <Sep />
      <span className="text-muted-foreground">re-scored 2h ago</span>
      <a href="#commit" className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
        view commit <ExternalLink className="size-2.5" />
      </a>
    </div>
  );
}

function Sep(): JSX.Element {
  return <span className="text-muted-foreground/40">·</span>;
}

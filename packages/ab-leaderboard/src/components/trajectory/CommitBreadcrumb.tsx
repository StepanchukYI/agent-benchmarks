import { ExternalLink, Github } from "lucide-react";
import { TrustDot } from "../domain/TrustDot";
import { fmtIsoRelative, shortSha } from "../../lib/format";
import type { TrajectoryViewHeader, TrajectoryViewTrust, TrustTier } from "../../lib/types";

const TRUST_TIERS: TrustTier[] = ["official", "verified", "self_reported"];

function asTrustTier(tier: string | null): TrustTier {
  return TRUST_TIERS.includes(tier as TrustTier) ? (tier as TrustTier) : "self_reported";
}

interface CommitBreadcrumbProps {
  trust: TrajectoryViewTrust;
  header: TrajectoryViewHeader;
}

/** Provenance strip: where it lives, which commit, run id, trust + re-score time. */
export function CommitBreadcrumb({ trust, header }: CommitBreadcrumbProps): JSX.Element {
  const tier = asTrustTier(trust.tier);
  const commit = trust.source_commit_sha;
  const repoUrl = trust.repo_url;
  return (
    <div className="flex items-center gap-2 px-6 py-1.5 bg-background-2 border-b border-border-soft text-[11px]">
      {repoUrl && (
        <>
          <a
            href={repoUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 font-mono text-muted-foreground hover:text-foreground"
          >
            <Github className="size-3" />
            {repoUrl.replace(/^https?:\/\//, "")}
          </a>
          <Sep />
        </>
      )}
      {commit && (
        <>
          <a
            href={repoUrl ? `${repoUrl}/commit/${commit}` : undefined}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-accent hover:underline"
          >
            {shortSha(commit)}
          </a>
          <Sep />
        </>
      )}
      {header.run_id && <span className="font-mono text-foreground-2">{header.run_id}</span>}
      <span className="flex-1" />
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <TrustDot tier={tier} size={11} commit={commit ?? undefined} />
        {tier}
      </span>
      {trust.re_scored_at && (
        <>
          <Sep />
          <span className="text-muted-foreground">re-scored {fmtIsoRelative(trust.re_scored_at)}</span>
        </>
      )}
      {repoUrl && commit && (
        <a
          href={`${repoUrl}/commit/${commit}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          view commit <ExternalLink className="size-2.5" />
        </a>
      )}
    </div>
  );
}

function Sep(): JSX.Element {
  return <span className="text-muted-foreground/40">·</span>;
}

import { cn } from "../../lib/utils";
import type { TrustTier } from "../../lib/types";
import { shortSha } from "../../lib/format";

interface TrustDotProps {
  tier: TrustTier;
  size?: number;
  commit?: string;
  className?: string;
}

/**
 * Glyph-only trust indicator: ● official, ◐ verified, ○ self-reported.
 * Hover tooltip explains the meaning and (optionally) the verified commit.
 */
export function TrustDot({ tier, size = 11, commit, className }: TrustDotProps): JSX.Element {
  const map: Record<TrustTier, { glyph: string; color: string; label: string }> = {
    official:      { glyph: "●", color: "text-pass",    label: `Official — verified at commit ${commit ? shortSha(commit) : ""}`.trim() },
    verified:      { glyph: "◐", color: "text-accent",  label: `Verified — re-scored by maintainer${commit ? " at " + shortSha(commit) : ""}` },
    self_reported: { glyph: "○", color: "text-muted-foreground", label: "Self-reported — server cannot re-verify" },
  };
  const def = map[tier];
  return (
    <span
      title={def.label}
      className={cn("inline-flex items-center justify-center leading-none cursor-help", def.color, className)}
      style={{ width: size + 4, height: size + 4, fontSize: size }}
      aria-label={def.label}
    >
      {def.glyph}
    </span>
  );
}

import { cn } from "../../lib/utils";
import { deltaArrow, deltaTone, fmtScore } from "../../lib/format";

interface ScoreCellProps {
  score: number | null | undefined;
  delta?: number | null;
  className?: string;
}

export function ScoreCell({ score, delta, className }: ScoreCellProps): JSX.Element {
  const tone = deltaTone(delta);
  return (
    <span className={cn("inline-flex items-baseline gap-1 tnum", className)}>
      <span className="font-semibold text-foreground text-[13px]">{fmtScore(score)}</span>
      {delta != null && (
        <span
          className={cn(
            "text-[10.5px] tnum",
            tone === "up" && "text-pass",
            tone === "dn" && "text-fail",
            tone === "flat" && "text-muted-foreground",
          )}
        >
          {deltaArrow(delta)} {Math.abs(delta).toFixed(1)}
        </span>
      )}
    </span>
  );
}

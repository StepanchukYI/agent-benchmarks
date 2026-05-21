import { Pill } from "../ui/Pill";
import type { Suite } from "../../lib/types";

export function SuiteChip({ suite }: { suite: Suite }): JSX.Element {
  return (
    <Pill tone="neutral" size="sm" noDot>
      <span className="font-mono text-muted-foreground">{suite.layer}</span>
      <span className="text-muted-foreground/60">·</span>
      <span>{suite.name}</span>
    </Pill>
  );
}

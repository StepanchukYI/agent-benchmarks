import { type ReactNode } from "react";
import { Pill, type PillSize, type PillTone } from "./Pill";
import type { RunStatus, TrustTier } from "../../lib/types";

interface StatusPillProps {
  kind: RunStatus | TrustTier | "needs-review" | "pass" | "fail" | "warn" | "info" | "idle";
  size?: PillSize;
  children?: ReactNode;
}

const STATUS_MAP: Record<string, { tone: PillTone; label: string }> = {
  pass:           { tone: "pass", label: "pass" },
  fail:           { tone: "fail", label: "fail" },
  warn:           { tone: "warn", label: "warn" },
  info:           { tone: "info", label: "info" },
  idle:           { tone: "idle", label: "idle" },
  completed:      { tone: "pass", label: "completed" },
  error:          { tone: "fail", label: "error" },
  timeout:        { tone: "warn", label: "timeout" },
  unrunnable:     { tone: "idle", label: "unrunnable" },
  running:        { tone: "accent", label: "running" },
  "needs-review": { tone: "warn", label: "needs review" },
  official:       { tone: "pass", label: "official" },
  verified:       { tone: "accent", label: "verified" },
  self_reported:  { tone: "idle", label: "self-reported" },
};

export function StatusPill({ kind, size = "md", children }: StatusPillProps): JSX.Element {
  const def = STATUS_MAP[kind] ?? { tone: "neutral" as const, label: kind };
  return (
    <Pill tone={def.tone} size={size}>
      {children ?? def.label}
    </Pill>
  );
}

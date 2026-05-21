import { Pill } from "../ui/Pill";
import type { DatasetPin } from "../../lib/types";

interface StaleDatasetPillProps {
  pin: DatasetPin;
}

/**
 * Shown only when the operator's pinned dataset version lags the current.
 * Severity is amber for 1-2 behind, red for ≥3.
 */
export function StaleDatasetPill({ pin }: StaleDatasetPillProps): JSX.Element | null {
  if (pin.behind === 0) return null;
  const severe = pin.behind >= 3;
  return (
    <Pill tone={severe ? "fail" : "warn"} size="sm" className="font-mono" noDot>
      {pin.version} · {pin.behind} behind
    </Pill>
  );
}

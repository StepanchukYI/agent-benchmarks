import { cn } from "../../lib/utils";
import type { Operator } from "../../lib/types";

interface AvatarProps {
  operator: Operator;
  size?: number;
  className?: string;
}

/**
 * Round avatar with operator initials. Self-operator gets an accent ring.
 */
export function Avatar({ operator, size = 18, className }: AvatarProps): JSX.Element {
  const fontSize = size <= 16 ? 8 : size <= 20 ? 9 : 10;
  return (
    <span
      aria-label={`@${operator.handle}`}
      title={`@${operator.handle}`}
      className={cn(
        "inline-grid place-items-center rounded-full font-semibold text-white shrink-0 leading-none select-none",
        operator.is_self && "ring-1 ring-accent",
        className,
      )}
      style={{
        width: size,
        height: size,
        backgroundColor: operator.color,
        fontSize,
        letterSpacing: "-0.02em",
      }}
    >
      {operator.initials}
    </span>
  );
}

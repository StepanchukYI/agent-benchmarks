import { type HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

interface CheckBoxProps extends Omit<HTMLAttributes<HTMLSpanElement>, "onChange"> {
  checked?: boolean;
  /** Variant for filter-rail rows where checks are visual only. */
  decorative?: boolean;
}

/**
 * Visual checkbox — keyboard accessibility is provided by the parent button or
 * label. Use the `checked` prop to drive the filled state.
 */
export function CheckBox({ checked = false, className, ...rest }: CheckBoxProps): JSX.Element {
  return (
    <span
      role="checkbox"
      aria-checked={checked}
      className={cn(
        "inline-grid place-items-center size-3.5 rounded-[4px] border border-border bg-panel-2 shrink-0",
        checked && "bg-accent border-accent",
        className,
      )}
      {...rest}
    >
      {checked && (
        <svg viewBox="0 0 12 12" className="size-2.5" aria-hidden>
          <path
            d="M2.5 6.2 5 8.5 9.5 3.5"
            stroke="white"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      )}
    </span>
  );
}

import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "../../lib/utils";

export type ButtonVariant = "default" | "primary" | "ghost" | "destructive";
export type ButtonSize = "sm" | "md" | "lg" | "icon" | "icon-sm";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const VARIANT: Record<ButtonVariant, string> = {
  default:
    "bg-panel-2 border border-border text-foreground hover:bg-panel-3 hover:border-border/80",
  primary:
    "bg-accent border border-accent text-accent-foreground hover:bg-accent/90 shadow-[inset_0_1px_0_rgba(255,255,255,.18)]",
  ghost:
    "bg-transparent border border-transparent text-muted-foreground hover:text-foreground hover:bg-panel-2",
  destructive:
    "bg-fail/[0.12] border border-fail/30 text-fail hover:bg-fail/[0.18]",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-6 px-2 text-[11px]",
  md: "h-7 px-3 text-[12px]",
  lg: "h-[34px] px-4 text-[13px]",
  icon: "h-7 w-7 p-0 justify-center",
  "icon-sm": "h-6 w-6 p-0 justify-center",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "default", size = "md", className, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none",
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      {...rest}
    />
  );
});

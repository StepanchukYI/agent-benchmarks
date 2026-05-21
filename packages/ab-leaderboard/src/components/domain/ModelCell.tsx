import { cn } from "../../lib/utils";
import type { Model, Vendor } from "../../lib/types";

interface ModelCellProps {
  model: Model;
  /** Show the harness name beneath the id. */
  showHarness?: boolean;
  /** Smaller text — used in table rows. */
  compact?: boolean;
}

const VENDOR_DOT_CLASS: Record<Vendor, string> = {
  anthropic: "bg-vendor-anthropic",
  openai:    "bg-vendor-openai",
  google:    "bg-vendor-google",
  zhipu:     "bg-vendor-zhipu",
  minimax:   "bg-vendor-minimax",
};

export function ModelCell({ model, showHarness = false, compact = false }: ModelCellProps): JSX.Element {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span className={cn("size-2 rounded-full shrink-0", VENDOR_DOT_CLASS[model.vendor])} />
      <span className="flex flex-col leading-tight">
        <span className={cn("font-mono font-medium text-foreground", compact ? "text-[11px]" : "text-[12px]")}>
          {model.id}
        </span>
        {showHarness && (
          <span className="text-muted-foreground text-[10.5px]">{model.harness}</span>
        )}
      </span>
    </span>
  );
}

export { VENDOR_DOT_CLASS };

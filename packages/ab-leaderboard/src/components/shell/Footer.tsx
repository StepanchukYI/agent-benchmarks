import { Github } from "lucide-react";
import { useVersion } from "../../api/hooks";

/**
 * Global footer — OSS posture, version marker, mode marker.
 *
 * Sticky bottom is intentionally avoided: pages with long scrolls (Trends
 * heatmap) push the footer down naturally and the user can reach it.
 */
export function Footer(): JSX.Element {
  const { data: version } = useVersion();
  return (
    <footer className="flex items-center justify-between gap-4 px-4 py-3 text-[11.5px] text-muted-foreground border-t border-border bg-background">
      <div className="flex items-center gap-2.5">
        <span>Open source · Apache 2.0</span>
        <Sep />
        <a
          href="https://github.com/StepanchukYI/agent-benchmarks"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 hover:text-foreground"
        >
          <Github className="size-3" />
          github.com/StepanchukYI/agent-benchmarks
        </a>
        <Sep />
        <a href="#discord" className="hover:text-foreground">Discord</a>
        <Sep />
        <a href="#docs" className="hover:text-foreground">Docs</a>
        <Sep />
        <a href="#cli" className="hover:text-foreground">
          CLI · ab{version ? ` v${version.server}` : ""}
        </a>
      </div>
      <div className="flex items-center gap-2.5">
        <span>pull-based aggregation · active</span>
      </div>
    </footer>
  );
}

function Sep(): JSX.Element {
  return <span className="size-[3px] rounded-full bg-muted-foreground/40" aria-hidden />;
}

import { Bell, Github, Moon, Search, Sun } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "../../lib/utils";
import { useTheme } from "../../lib/theme";
import { Avatar } from "../ui/Avatar";
import { Kbd } from "../ui/Tag";
import { Button } from "../ui/Button";
import { useOperators } from "../../api/hooks";

interface TopNavProps {
  /** When false, show "Sign in with GitHub" instead of the avatar. */
  signedIn?: boolean;
  /** Handle used as the signed-in identity. Mock-only. */
  selfHandle?: string;
  /** Counts for the top tab badges. */
  counts?: Partial<Record<"runs" | "tasks", number>>;
}

interface TabDef {
  to: string;
  label: string;
  countKey?: "runs" | "tasks";
}

const TABS: TabDef[] = [
  { to: "/runs", label: "Runs", countKey: "runs" },
  { to: "/tasks", label: "Tasks", countKey: "tasks" },
  { to: "/leaderboard", label: "Leaderboard" },
  { to: "/trends", label: "Trends" },
  { to: "/settings", label: "Settings" },
];

export function TopNav({ signedIn = true, selfHandle = "evgeniy", counts = {} }: TopNavProps): JSX.Element {
  const { theme, toggleTheme } = useTheme();
  const { data: operators } = useOperators();
  const self = (operators ?? []).find((o) => o.handle === selfHandle);

  return (
    <header className="h-[50px] sticky top-0 z-30 flex items-center gap-5 px-4 border-b border-border bg-gradient-to-b from-panel to-background">
      <div className="flex items-center gap-2.5 text-[13px] font-semibold tracking-tight">
        <span className="grid place-items-center size-[22px] rounded-md bg-gradient-to-br from-accent to-indigo-600 text-white shadow-[0_2px_8px_rgba(59,130,246,0.35),inset_0_1px_0_rgba(255,255,255,0.25)]">
          <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M4 21V8l8-5 8 5v13" />
            <path d="M9 21V12h6v9" />
          </svg>
        </span>
        <span>agent-benchmarks</span>
        <span className="font-mono font-normal text-[11px] text-muted-foreground pt-[1px]">v0.5.0</span>
      </div>

      <nav className="flex gap-0.5 ml-2">
        {TABS.map(({ to, label, countKey }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[13px] font-medium transition-colors",
                isActive
                  ? "bg-panel-2 text-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-panel-2",
              )
            }
          >
            <span>{label}</span>
            {countKey && counts[countKey] != null && (
              <span className="text-[10.5px] tnum px-1 py-[1px] rounded bg-panel-3 text-muted-foreground">
                {counts[countKey]}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="flex-1" />

      <button
        type="button"
        className="h-7 w-[260px] inline-flex items-center gap-2 px-2.5 rounded-md border border-border bg-panel-2 text-[12px] text-muted-foreground hover:text-foreground"
      >
        <Search className="size-3.5" />
        <span className="flex-1 text-left">Search runs, tasks, models…</span>
        <Kbd>⌘K</Kbd>
      </button>

      <button
        type="button"
        title="Pull-aggregation status"
        className="h-7 w-7 grid place-items-center rounded-md border border-border bg-panel-2 hover:bg-panel-3"
      >
        <span className="relative size-2">
          <span className="absolute inset-0 rounded-full bg-pass" />
          <span className="absolute -inset-1 rounded-full bg-pass/30 animate-pulse-ring" />
        </span>
      </button>

      <Button variant="default" size="icon" title="Notifications">
        <Bell className="size-3.5" />
      </Button>

      <Button variant="default" size="icon" title="Toggle theme" onClick={toggleTheme}>
        {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
      </Button>

      {signedIn && self ? (
        <button
          type="button"
          className="flex items-center gap-2 h-7 px-1 pr-2 rounded-full border border-transparent hover:bg-panel-2 hover:border-border"
          title={`@${self.handle} · signed in via GitHub`}
        >
          <Avatar operator={self} size={22} />
          <span className="font-mono text-[11.5px] text-foreground-2">@{self.handle}</span>
        </button>
      ) : (
        <button
          type="button"
          className="h-7 px-3 inline-flex items-center gap-2 rounded-md border border-border bg-foreground text-background text-[12px] font-medium hover:bg-foreground/90"
        >
          <Github className="size-3.5" />
          Sign in with GitHub
        </button>
      )}
    </header>
  );
}

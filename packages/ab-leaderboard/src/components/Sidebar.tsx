import { Activity, LayoutGrid, LineChart, Play, Settings as SettingsIcon } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "../lib/utils";

type NavItem = {
  to: string;
  label: string;
  icon: typeof LayoutGrid;
};

const items: NavItem[] = [
  { to: "/leaderboard", label: "Leaderboard", icon: LayoutGrid },
  { to: "/runs", label: "Run Launcher", icon: Play },
  { to: "/trajectories", label: "Trajectories", icon: Activity },
  { to: "/trends", label: "Trends", icon: LineChart },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function Sidebar(): JSX.Element {
  return (
    <aside className="w-56 border-r border-border bg-muted/30 p-4">
      <div className="mb-6 px-2 text-sm font-semibold tracking-tight">agent-benchmarks</div>
      <nav className="flex flex-col gap-1">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-foreground hover:bg-accent hover:text-accent-foreground",
              )
            }
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

import { Bell, Box, Cog, Folder, Github, Key, KeyRound, Network, ShieldCheck, Zap } from "lucide-react";
import { type ElementType } from "react";
import { cn } from "../../lib/utils";
import { useConnectedRepos, useModels, useTokensList } from "../../api/hooks";

export type SettingsTab = "account" | "repos" | "tokens" | "privacy" | "models" | "mcp" | "skills" | "vaults" | "ci" | "alerts";

interface SettingsSidebarProps {
  active: SettingsTab;
  onSelect: (t: SettingsTab) => void;
}

interface SidebarItem {
  id: SettingsTab;
  label: string;
  icon: ElementType<{ className?: string }>;
  count?: number;
}

export function SettingsSidebar({ active, onSelect }: SettingsSidebarProps): JSX.Element {
  const { data: connectedRepos } = useConnectedRepos();
  const { data: models } = useModels();
  const { data: tokens } = useTokensList();
  const activeTokenCount = (tokens ?? []).filter((t) => t.revoked_at == null).length;
  const items: SidebarItem[] = [
    { id: "account",  label: "Account",         icon: Github },
    { id: "repos",    label: "Connected repos", icon: KeyRound, count: (connectedRepos ?? []).length },
    { id: "tokens",   label: "API tokens",      icon: Key,      count: activeTokenCount },
    { id: "privacy",  label: "Privacy",         icon: ShieldCheck },
    { id: "models",   label: "Models",          icon: Box,      count: (models ?? []).length },
    { id: "mcp",      label: "MCP servers",     icon: Network,  count: 11 },
    { id: "skills",   label: "Skills",          icon: Zap,      count: 47 },
    { id: "vaults",   label: "Vault snapshots", icon: Folder,   count: 3 },
    { id: "ci",       label: "CI gate",         icon: Cog },
    { id: "alerts",   label: "Alert channels",  icon: Bell,     count: 2 },
  ];
  return (
    <aside className="w-[220px] shrink-0 border-r border-border bg-background-2 overflow-y-auto">
      <div className="px-3.5 pt-3 pb-1.5 text-[10.5px] uppercase tracking-wider font-semibold text-muted-foreground">
        Settings
      </div>
      <nav className="flex flex-col">
        {items.map((it) => {
          const Icon = it.icon;
          return (
            <button
              key={it.id}
              type="button"
              onClick={() => onSelect(it.id)}
              className={cn(
                "flex items-center gap-2.5 px-3.5 py-1.5 text-[12px] border-l-2 text-left",
                active === it.id
                  ? "bg-accent/[0.12] text-foreground border-accent"
                  : "border-transparent text-foreground-2 hover:bg-panel-2",
              )}
            >
              <Icon className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="flex-1">{it.label}</span>
              {it.count != null && (
                <span className="text-muted-foreground text-[11px] tnum">{it.count}</span>
              )}
            </button>
          );
        })}
      </nav>
      <div className="px-3.5 py-3 mt-2">
        <p className="text-[10.5px] text-muted-foreground leading-relaxed">
          GitHub-OAuth aggregation per <span className="font-mono">ADR-007</span>.
          Privacy scrubber per <span className="font-mono">LSN-006</span>.
        </p>
      </div>
    </aside>
  );
}

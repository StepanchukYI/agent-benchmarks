import { GitBranch, Info, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Panel } from "../ui/Panel";
import { Button } from "../ui/Button";
import { StatusPill } from "../ui/StatusPill";
import { Callout } from "../ui/Callout";
import { EmptyState } from "../ui/EmptyState";
import { ErrorBanner } from "../ui/ErrorBanner";
import { LoadingSkeleton } from "../ui/LoadingSkeleton";
import { PageHero } from "../shell/PageHero";
import { OperatorTag } from "../domain/OperatorTag";
import {
  useConnectedRepos,
  useDeleteRepo,
  useOperators,
  useSyncRepo,
} from "../../api/hooks";
import { toState } from "../../lib/ui-state";
import type { RegistryRepo } from "../../lib/types";
import { AddRepoModal } from "./AddRepoModal";

const STATUS_TONE: Record<RegistryRepo["status"], "pass" | "warn" | "fail"> = {
  ok: "pass",
  pending: "warn",
  failed: "fail",
};

export function ReposTab(): JSX.Element {
  const reposQuery = useConnectedRepos();
  const reposState = toState(reposQuery);
  const { data: operators } = useOperators();
  const operatorList = operators ?? [];
  const syncRepo = useSyncRepo();
  const deleteRepo = useDeleteRepo();
  const [addOpen, setAddOpen] = useState(false);

  async function syncAll(): Promise<void> {
    const repos = reposQuery.data ?? [];
    for (const r of repos) {
      if (!r.id || r.id.startsWith("mock-")) continue;
      try {
        await syncRepo.mutateAsync(r.id);
      } catch {
        // Continue with the next repo; per-repo errors surface in
        // `last_synced` / `status` columns after the refetch.
      }
    }
    reposQuery.refetch();
  }

  return (
    <>
      <PageHero
        className="px-0 border-b-0 pt-0"
        title="Connected repos"
        subtitle={
          <>
            Pull-based aggregation per{" "}
            <a className="text-accent hover:underline" href="#adr-007">ADR-007</a>.
            Each repo's results are fetched and re-scored when the maintainer can re-verify.
          </>
        }
        actions={
          <>
            <Button onClick={syncAll} disabled={syncRepo.isPending}>
              <RefreshCw className="size-3" /> Sync all
            </Button>
            <Button variant="primary" onClick={() => setAddOpen(true)}>
              <Plus className="size-3" /> Add repo
            </Button>
          </>
        }
      />

      {reposState.kind === "loading" && <LoadingSkeleton rows={4} columns={6} />}
      {reposState.kind === "error" && (
        <ErrorBanner
          message={reposState.message}
          retry={() => reposQuery.refetch()}
        />
      )}
      {reposState.kind === "empty" && (
        <EmptyState
          title="No repos connected yet."
          hint={
            <>
              Use{" "}
              <span className="font-mono text-foreground-2">ab register github.com/&lt;handle&gt;/&lt;repo&gt;</span>{" "}
              or click Add repo above.
            </>
          }
        />
      )}
      {reposState.kind === "ok" && (
        <Panel className="overflow-hidden">
          <table className="w-full text-[12px] border-collapse">
            <thead>
              <tr className="text-left text-muted-foreground text-[11px]">
                <th className="px-3.5 py-2 border-b border-border font-medium">Repo</th>
                <th className="px-3.5 py-2 border-b border-border font-medium">Owner</th>
                <th className="px-3.5 py-2 border-b border-border font-medium">Branch</th>
                <th className="px-3.5 py-2 border-b border-border font-medium text-right">Runs</th>
                <th className="px-3.5 py-2 border-b border-border font-medium">Last synced</th>
                <th className="px-3.5 py-2 border-b border-border font-medium">Status</th>
                <th className="px-3.5 py-2 border-b border-border w-[80px]" />
              </tr>
            </thead>
            <tbody>
              {reposState.value.map((r) => {
                const op = operatorList.find((o) => o.handle === r.owner);
                return (
                  <tr key={r.repo} className="hover:bg-panel-2/50">
                    <td className="px-3.5 py-2.5 border-b border-border-soft font-mono text-[11.5px]">
                      <GitBranch className="inline size-3 mr-1 text-muted-foreground" />
                      {r.repo}
                    </td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft">
                      {op && <OperatorTag handle={op.handle} avatarSize={14} />}
                    </td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft font-mono text-muted-foreground">{r.branch}</td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft text-right tnum">{r.runs}</td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft text-muted-foreground">{r.last_synced}</td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft">
                      <span title={r.error}>
                        <StatusPill kind={STATUS_TONE[r.status]} size="sm">
                          {r.status === "ok" ? "ok" : r.status === "pending" ? "syncing" : "failed"}
                        </StatusPill>
                      </span>
                    </td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          disabled={!r.id || r.id.startsWith("mock-") || syncRepo.isPending}
                          onClick={() => r.id && syncRepo.mutate(r.id)}
                          title="Sync now"
                        >
                          <RefreshCw className="size-3" />
                        </Button>
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          disabled={!r.id || r.id.startsWith("mock-") || deleteRepo.isPending}
                          onClick={() => {
                            if (!r.id) return;
                            if (confirm(`Disconnect ${r.repo}?`)) {
                              deleteRepo.mutate(r.id);
                            }
                          }}
                          title="Disconnect"
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>
      )}

      <Callout tone="accent" icon={<Info className="size-3.5" />}>
        To add a repo via CLI:{" "}
        <span className="font-mono text-foreground">ab register github.com/&lt;handle&gt;/&lt;repo&gt;</span>.
        The repo must contain a top-level <span className="font-mono">/ab/runs/</span> directory
        matching the schema.
      </Callout>

      <AddRepoModal open={addOpen} onOpenChange={setAddOpen} />
    </>
  );
}

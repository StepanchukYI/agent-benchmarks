import PageShell from "../components/PageShell";

export default function TrajectoryViewer(): JSX.Element {
  return (
    <PageShell title="Trajectory Viewer">
      <div className="rounded-lg border border-border bg-card p-6 text-card-foreground shadow-sm">
        <p className="text-sm text-muted-foreground">
          Trajectory Viewer — Phase 0 placeholder. Wire up{" "}
          <code>/api/v1/runs/{`{id}`}/trajectories/{`{task_id}`}</code> in Phase 1 row 13.
        </p>
      </div>
    </PageShell>
  );
}

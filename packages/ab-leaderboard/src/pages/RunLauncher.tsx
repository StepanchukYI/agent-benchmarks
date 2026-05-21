import PageShell from "../components/PageShell";

export default function RunLauncher(): JSX.Element {
  return (
    <PageShell title="Run Launcher">
      <div className="rounded-lg border border-border bg-card p-6 text-card-foreground shadow-sm">
        <p className="text-sm text-muted-foreground">
          Run Launcher — Phase 0 placeholder. Wire up <code>POST /api/v1/runs</code> in Phase 1 row 12.
        </p>
      </div>
    </PageShell>
  );
}

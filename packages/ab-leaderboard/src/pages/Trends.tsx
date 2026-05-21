import PageShell from "../components/PageShell";

export default function Trends(): JSX.Element {
  return (
    <PageShell title="Trends">
      <div className="rounded-lg border border-border bg-card p-6 text-card-foreground shadow-sm">
        <p className="text-sm text-muted-foreground">
          Trends — Phase 0 placeholder. Wire up <code>/api/v1/trends</code> in Phase 1 row 14.
        </p>
      </div>
    </PageShell>
  );
}

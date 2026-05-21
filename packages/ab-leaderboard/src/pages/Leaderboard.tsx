import PageShell from "../components/PageShell";

export default function Leaderboard(): JSX.Element {
  return (
    <PageShell title="Leaderboard">
      <div className="rounded-lg border border-border bg-card p-6 text-card-foreground shadow-sm">
        <p className="text-sm text-muted-foreground">
          Leaderboard — Phase 0 placeholder. Wire up <code>/api/v1/leaderboard</code> in Phase 1 row 11.
        </p>
      </div>
    </PageShell>
  );
}

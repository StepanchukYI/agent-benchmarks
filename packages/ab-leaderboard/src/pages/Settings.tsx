import PageShell from "../components/PageShell";

export default function Settings(): JSX.Element {
  return (
    <PageShell title="Settings">
      <div className="rounded-lg border border-border bg-card p-6 text-card-foreground shadow-sm">
        <p className="text-sm text-muted-foreground">
          Settings — Phase 0 placeholder. Wire up GitHub OAuth + registered repos in Phase 1 row 15.
        </p>
      </div>
    </PageShell>
  );
}

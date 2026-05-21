import { Eye, Github } from "lucide-react";
import { useState } from "react";

import { useMe, useSignOut } from "../../api/hooks";
import { Button } from "../ui/Button";
import { Panel, PanelHeader } from "../ui/Panel";
import { PageHero } from "../shell/PageHero";
import { SignInModal } from "./SignInModal";

interface Toggle {
  label: string;
  sub: string;
  on: boolean;
}

const TOGGLES: Toggle[] = [
  { label: "Show my runs on the public leaderboard", sub: "Only runs published via `ab publish` (after scrubber).",                on: true },
  { label: "Show my regressions in the friends feed", sub: "Only connected friends can see these.",                                on: true },
  { label: "Allow others to replay my commits",       sub: "Anyone with the commit URL can re-run.",                              on: true },
  { label: "Auto-scrub vault paths before publishing", sub: "Recommended. Disable only if you publish from a non-personal vault.", on: true },
];

export function AccountTab(): JSX.Element {
  const meQuery = useMe();
  const signOut = useSignOut();
  const [signInOpen, setSignInOpen] = useState(false);

  const me = meQuery.data;
  const initials = me ? me.handle.slice(0, 2).toUpperCase() : "??";

  return (
    <>
      <PageHero
        title="Account"
        subtitle="GitHub identity, sign-in, and global preferences."
        className="px-0 border-b-0 pt-0"
      />

      <Panel>
        <PanelHeader title={<span className="inline-flex items-center gap-2"><Github className="size-3.5" /> GitHub identity</span>} />
        <div className="p-5 flex items-center gap-4">
          {meQuery.isLoading ? (
            <div className="text-[12.5px] text-muted-foreground">Checking session…</div>
          ) : me ? (
            <>
              <div className="size-12 grid place-items-center rounded-full bg-gradient-to-br from-accent to-indigo-500 text-white font-bold text-base">
                {initials}
              </div>
              <div className="flex-1">
                <div className="font-semibold text-[14px]">
                  {me.handle}
                  <span className="text-muted-foreground font-normal"> · @{me.handle}</span>
                </div>
                <div className="text-[11.5px] text-muted-foreground mt-0.5">
                  Signed in via GitHub OAuth · scopes: <span className="font-mono">read:user, public_repo</span>
                </div>
                <div className="text-[11.5px] text-muted-foreground">
                  github_id: <span className="font-mono">{me.github_id}</span>
                </div>
              </div>
              <Button onClick={() => setSignInOpen(true)}>Re-authorize</Button>
              <Button variant="destructive" onClick={() => signOut.mutate()}>Sign out</Button>
            </>
          ) : (
            <>
              <div className="size-12 grid place-items-center rounded-full bg-panel-3 text-muted-foreground">
                <Github className="size-5" />
              </div>
              <div className="flex-1">
                <div className="font-semibold text-[14px]">Not signed in</div>
                <div className="text-[11.5px] text-muted-foreground mt-0.5">
                  Sign in to register a results repo, publish runs, and see your trust tier.
                </div>
              </div>
              <Button onClick={() => setSignInOpen(true)}>Sign in with GitHub</Button>
            </>
          )}
        </div>
      </Panel>

      <Panel>
        <PanelHeader title={<span className="inline-flex items-center gap-2"><Eye className="size-3.5" /> Visibility</span>} />
        <div className="p-4 flex flex-col gap-3">
          {TOGGLES.map((t, i) => (
            <div
              key={t.label}
              className={
                "flex items-center gap-3.5 py-2 " +
                (i < TOGGLES.length - 1 ? "border-b border-border-soft" : "")
              }
            >
              <div className="flex-1">
                <div className="text-[12.5px] font-medium">{t.label}</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">{t.sub}</div>
              </div>
              <Switch on={t.on} />
            </div>
          ))}
        </div>
      </Panel>

      <SignInModal open={signInOpen} onOpenChange={setSignInOpen} />
    </>
  );
}

function Switch({ on }: { on: boolean }): JSX.Element {
  return (
    <div
      className={`w-8 h-[18px] rounded-full p-[2px] transition-colors ${on ? "bg-accent" : "bg-panel-3"}`}
      role="switch"
      aria-checked={on}
    >
      <div
        className={`size-3.5 rounded-full bg-white transition-transform ${on ? "translate-x-[14px]" : "translate-x-0"}`}
      />
    </div>
  );
}

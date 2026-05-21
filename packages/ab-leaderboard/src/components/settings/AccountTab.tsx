import { Eye, Github } from "lucide-react";
import { useState } from "react";

import { useMe, useSignOut, useUpdateMeVisibility } from "../../api/hooks";
import { Button } from "../ui/Button";
import { ErrorBanner } from "../ui/ErrorBanner";
import { Panel, PanelHeader } from "../ui/Panel";
import { PageHero } from "../shell/PageHero";
import { PostLoginGuide } from "./PostLoginGuide";
import { SignInModal } from "./SignInModal";

type VisibilityField = "public_profile" | "share_runs";

interface ToggleSpec {
  field: VisibilityField;
  label: string;
  sub: string;
}

const VISIBILITY_TOGGLES: ToggleSpec[] = [
  {
    field: "public_profile",
    label: "Show my profile on the public leaderboard",
    sub: "When off, rows attributed to your handle are hidden from anonymous viewers.",
  },
  {
    field: "share_runs",
    label: "Share my published runs with friends",
    sub: "Only runs published via `ab publish` (after scrubber).",
  },
];

export function AccountTab(): JSX.Element {
  const meQuery = useMe();
  const signOut = useSignOut();
  const updateVisibility = useUpdateMeVisibility();
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

      {me && <PostLoginGuide />}

      {me && (
        <Panel>
          <PanelHeader title={<span className="inline-flex items-center gap-2"><Eye className="size-3.5" /> Visibility</span>} />
          {updateVisibility.isError && (
            <div className="px-4 pt-3">
              <ErrorBanner
                message={
                  updateVisibility.error instanceof Error
                    ? updateVisibility.error.message
                    : "Failed to update visibility."
                }
                retry={() => updateVisibility.reset()}
              />
            </div>
          )}
          <div className="p-4 flex flex-col gap-3">
            {VISIBILITY_TOGGLES.map((t, i) => {
              const checked = me[t.field];
              const pendingField =
                updateVisibility.isPending
                  ? Object.keys(updateVisibility.variables ?? {})[0]
                  : null;
              const isPendingHere = pendingField === t.field;
              return (
                <div
                  key={t.field}
                  className={
                    "flex items-center gap-3.5 py-2 " +
                    (i < VISIBILITY_TOGGLES.length - 1 ? "border-b border-border-soft" : "")
                  }
                >
                  <div className="flex-1">
                    <div className="text-[12.5px] font-medium">{t.label}</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">{t.sub}</div>
                  </div>
                  <Switch
                    on={checked}
                    disabled={updateVisibility.isPending}
                    busy={isPendingHere}
                    onToggle={() =>
                      updateVisibility.mutate({ [t.field]: !checked })
                    }
                    ariaLabel={t.label}
                  />
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      <SignInModal open={signInOpen} onOpenChange={setSignInOpen} />
    </>
  );
}

interface SwitchProps {
  on: boolean;
  disabled?: boolean;
  busy?: boolean;
  onToggle?: () => void;
  ariaLabel?: string;
}

function Switch({ on, disabled, busy, onToggle, ariaLabel }: SwitchProps): JSX.Element {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled || !onToggle}
      aria-label={ariaLabel}
      className={
        `w-8 h-[18px] rounded-full p-[2px] transition-colors ${on ? "bg-accent" : "bg-panel-3"} ` +
        `${disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer"} ` +
        `${busy ? "ring-2 ring-accent/40" : ""}`
      }
      role="switch"
      aria-checked={on}
    >
      <div
        className={`size-3.5 rounded-full bg-white transition-transform ${on ? "translate-x-[14px]" : "translate-x-0"}`}
      />
    </button>
  );
}

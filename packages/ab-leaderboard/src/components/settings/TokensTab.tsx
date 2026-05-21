/**
 * Settings → API tokens.
 *
 * CRUD over `/account/tokens`. Mirrors the ReposTab shape (PageHero header
 * + table + Callout footer) and uses the same loading/empty/error machinery.
 *
 * Plaintext token is shown exactly once after creation, inside a modal with
 * a copy-to-clipboard button. Dismissing the modal clears the secret from
 * component state — it is never persisted.
 */

import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, Check, Copy, Info, Key, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import { useCreateToken, useRevokeToken, useTokensList } from "../../api/hooks";
import type { ApiTokenCreated } from "../../lib/types";
import { toState } from "../../lib/ui-state";
import { PageHero } from "../shell/PageHero";
import { Button } from "../ui/Button";
import { Callout } from "../ui/Callout";
import { EmptyState } from "../ui/EmptyState";
import { ErrorBanner } from "../ui/ErrorBanner";
import { LoadingSkeleton } from "../ui/LoadingSkeleton";
import { Panel } from "../ui/Panel";
import { StatusPill } from "../ui/StatusPill";

function fmtTimestamp(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().replace("T", " ").slice(0, 16) + "Z";
  } catch {
    return iso;
  }
}

export function TokensTab(): JSX.Element {
  const tokensQuery = useTokensList();
  const tokensState = toState(tokensQuery);
  const createToken = useCreateToken();
  const revokeToken = useRevokeToken();

  const [createOpen, setCreateOpen] = useState(false);
  const [revealed, setRevealed] = useState<ApiTokenCreated | null>(null);

  return (
    <>
      <PageHero
        className="px-0 border-b-0 pt-0"
        title="API tokens"
        subtitle={
          <>
            Personal access tokens for the <span className="font-mono">ab</span>{" "}
            CLI and CI runners. Each token authenticates as your GitHub identity
            and inherits your repo permissions.
          </>
        }
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            <Plus className="size-3" /> New token
          </Button>
        }
      />

      {tokensState.kind === "loading" && <LoadingSkeleton rows={3} columns={5} />}
      {tokensState.kind === "error" && (
        <ErrorBanner
          message={tokensState.message}
          retry={() => tokensQuery.refetch()}
        />
      )}
      {tokensState.kind === "empty" && (
        <EmptyState
          title="No API tokens yet."
          hint={
            <>
              Create one with{" "}
              <span className="font-mono text-foreground-2">ab tokens create &lt;name&gt;</span>{" "}
              or click New token above.
            </>
          }
        />
      )}
      {tokensState.kind === "ok" && (
        <Panel className="overflow-hidden">
          <table className="w-full text-[12px] border-collapse">
            <thead>
              <tr className="text-left text-muted-foreground text-[11px]">
                <th className="px-3.5 py-2 border-b border-border font-medium">Name</th>
                <th className="px-3.5 py-2 border-b border-border font-medium">Prefix</th>
                <th className="px-3.5 py-2 border-b border-border font-medium">Created</th>
                <th className="px-3.5 py-2 border-b border-border font-medium">Last used</th>
                <th className="px-3.5 py-2 border-b border-border font-medium">Status</th>
                <th className="px-3.5 py-2 border-b border-border w-[60px]" />
              </tr>
            </thead>
            <tbody>
              {tokensState.value.map((t) => {
                const revoked = t.revoked_at != null;
                return (
                  <tr key={t.id} className="hover:bg-panel-2/50">
                    <td className="px-3.5 py-2.5 border-b border-border-soft">
                      <Key className="inline size-3 mr-1 text-muted-foreground" />
                      {t.name}
                    </td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft font-mono text-[11.5px] text-muted-foreground">
                      {t.prefix}…
                    </td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft text-muted-foreground tnum">
                      {fmtTimestamp(t.created_at)}
                    </td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft text-muted-foreground tnum">
                      {fmtTimestamp(t.last_used_at)}
                    </td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft">
                      <StatusPill kind={revoked ? "fail" : "pass"} size="sm">
                        {revoked ? "revoked" : "active"}
                      </StatusPill>
                    </td>
                    <td className="px-3.5 py-2.5 border-b border-border-soft">
                      <div className="flex justify-end">
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          disabled={revoked || revokeToken.isPending}
                          onClick={() => {
                            if (confirm(`Revoke token "${t.name}"? This cannot be undone.`)) {
                              revokeToken.mutate(t.id);
                            }
                          }}
                          title={revoked ? "already revoked" : "Revoke"}
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
        Tokens are scoped to your account. The plaintext value is shown once on
        creation — store it in a secret manager. Use{" "}
        <span className="font-mono text-foreground">ab tokens revoke &lt;id&gt;</span>{" "}
        from the CLI to revoke from anywhere.
      </Callout>

      <CreateTokenModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(t) => {
          setCreateOpen(false);
          setRevealed(t);
        }}
        submitting={createToken.isPending}
        submit={(name) => createToken.mutateAsync({ name })}
      />

      <RevealTokenModal token={revealed} onClose={() => setRevealed(null)} />
    </>
  );
}

/* ─── Create modal ──────────────────────────────────────────────────────── */

interface CreateModalProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onCreated: (t: ApiTokenCreated) => void;
  submitting: boolean;
  submit: (name: string) => Promise<ApiTokenCreated>;
}

function CreateTokenModal({
  open,
  onOpenChange,
  onCreated,
  submitting,
  submit,
}: CreateModalProps): JSX.Element {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setName("");
    setError(null);
  }

  async function onSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setError("name is required");
      return;
    }
    try {
      const created = await submit(trimmed);
      reset();
      onCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 w-[440px] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-background p-6 shadow-xl"
          onEscapeKeyDown={() => onOpenChange(false)}
        >
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="flex items-center gap-2 font-semibold text-[14px]">
              <Key className="size-4" /> New API token
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="text-muted-foreground hover:text-foreground"
                aria-label="close"
              >
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </div>

          <Dialog.Description className="text-[11.5px] text-muted-foreground mb-4">
            Give this token a memorable name so you can identify it later.
            The plaintext value will be shown once after creation.
          </Dialog.Description>

          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11.5px] text-foreground-2">Name</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. laptop, ci-runner"
                className="h-8 px-2 rounded-md border border-border bg-panel-2 text-[12.5px] font-mono"
                autoFocus
              />
            </label>

            {error && <div className="text-[11.5px] text-fail">{error}</div>}

            <div className="flex justify-end gap-2 mt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={submitting}>
                {submitting ? "Creating…" : "Create token"}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ─── Reveal-once modal ─────────────────────────────────────────────────── */

function RevealTokenModal({
  token,
  onClose,
}: {
  token: ApiTokenCreated | null;
  onClose: () => void;
}): JSX.Element {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard blocked — user can still select manually
    }
  }

  return (
    <Dialog.Root
      open={token !== null}
      onOpenChange={(next) => {
        if (!next) {
          setCopied(false);
          onClose();
        }
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 w-[520px] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-background p-6 shadow-xl"
          onEscapeKeyDown={() => onClose()}
        >
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="flex items-center gap-2 font-semibold text-[14px]">
              <Key className="size-4 text-accent" /> Token created
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="text-muted-foreground hover:text-foreground"
                aria-label="close"
              >
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </div>

          {token && (
            <>
              <Dialog.Description className="text-[11.5px] text-muted-foreground mb-3">
                <span className="font-mono text-foreground-2">{token.name}</span>
                {" "}— copy this token now. It will not be shown again.
              </Dialog.Description>

              <div className="mb-3 flex items-center gap-2">
                <pre className="flex-1 min-w-0 overflow-x-auto rounded-md border border-border bg-panel-2 px-2.5 py-1.5 text-[11.5px] font-mono text-foreground-2">
                  <code>{token.token}</code>
                </pre>
                <button
                  onClick={copy}
                  className="size-8 grid place-items-center rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-panel-3"
                  title={copied ? "copied" : "copy token"}
                  aria-label="copy token"
                >
                  {copied ? (
                    <Check className="size-3.5 text-pass" />
                  ) : (
                    <Copy className="size-3.5" />
                  )}
                </button>
              </div>

              <Callout tone="warn" icon={<AlertTriangle className="size-3.5" />}>
                This token will not be shown again. Store it in a secret manager
                now. If you lose it, revoke it and create a new one.
              </Callout>

              <div className="flex justify-end mt-4">
                <Button variant="primary" onClick={onClose}>
                  Done
                </Button>
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

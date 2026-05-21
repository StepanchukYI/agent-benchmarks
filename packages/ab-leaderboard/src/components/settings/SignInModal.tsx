/**
 * Modal that drives the GitHub device-flow login.
 *
 *   1. POSTs /auth/github/device-start, shows verification code
 *   2. Opens verification_uri in a new tab
 *   3. Polls /auth/github/device-poll every `interval` seconds
 *   4. On success, stores token in localStorage and invalidates /me
 */

import * as Dialog from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { Copy, ExternalLink, Github, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { runDeviceFlow, type DeviceCodeResponse } from "../../api/auth";
import { Button } from "../ui/Button";

export function SignInModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}): JSX.Element {
  const [code, setCode] = useState<DeviceCodeResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "waiting" | "ok" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    if (!open) {
      abortRef.current?.abort();
      abortRef.current = null;
      setCode(null);
      setStatus("idle");
      setError(null);
    }
  }, [open]);

  async function start(): Promise<void> {
    setStatus("waiting");
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await runDeviceFlow(
        (resp) => {
          setCode(resp);
          try {
            window.open(resp.verification_uri, "_blank", "noopener,noreferrer");
          } catch {
            // popup blocked — user uses copy button
          }
        },
        { signal: controller.signal },
      );
      setStatus("ok");
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
      onOpenChange(false);
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function copyCode(): Promise<void> {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code.user_code);
    } catch {
      // best-effort
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-40" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 w-[420px] rounded-md bg-panel border border-border shadow-xl p-5"
        >
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-[14px] font-semibold inline-flex items-center gap-2">
              <Github className="size-3.5" /> Sign in with GitHub
            </Dialog.Title>
            <Dialog.Close asChild>
              <button aria-label="Close" className="text-muted-foreground hover:text-foreground">
                <X className="size-3.5" />
              </button>
            </Dialog.Close>
          </div>

          {status === "idle" && (
            <div className="space-y-3">
              <p className="text-[12.5px] text-muted-foreground">
                The device flow uses GitHub's official browser endpoint. You'll see a
                code below, open a new tab automatically, paste the code, approve.
              </p>
              <Button onClick={start} className="w-full">Start sign-in</Button>
            </div>
          )}

          {status === "waiting" && code && (
            <div className="space-y-3">
              <div className="text-[12px] text-muted-foreground">Enter this code:</div>
              <div className="flex items-center gap-2">
                <code className="flex-1 font-mono text-[18px] tracking-widest text-center py-2 bg-panel-2 rounded border border-border">
                  {code.user_code}
                </code>
                <Button onClick={copyCode} variant="default" aria-label="Copy code">
                  <Copy className="size-3" />
                </Button>
              </div>
              <a
                href={code.verification_uri}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline"
              >
                Open verification page <ExternalLink className="size-3" />
              </a>
              <div className="text-[11px] text-muted-foreground">
                Polling every {code.interval}s, expires in {Math.round(code.expires_in / 60)}m.
              </div>
            </div>
          )}

          {status === "error" && (
            <div className="space-y-3">
              <div className="text-[12.5px] text-red-400">Sign-in failed: {error}</div>
              <Button onClick={start} variant="default" className="w-full">Try again</Button>
            </div>
          )}

          {status === "waiting" && !code && (
            <div className="text-[12.5px] text-muted-foreground">Contacting GitHub…</div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

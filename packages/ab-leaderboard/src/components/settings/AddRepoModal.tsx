/**
 * Modal to register a results repo. POST /repos via useRegisterRepo;
 * server then schedules the fetcher to clone + ingest the repo's
 * /ab/runs/ tree.
 */

import * as Dialog from "@radix-ui/react-dialog";
import { GitBranch, X } from "lucide-react";
import { useState } from "react";

import { useRegisterRepo } from "../../api/hooks";
import { Button } from "../ui/Button";

export function AddRepoModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}): JSX.Element {
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [error, setError] = useState<string | null>(null);
  const register = useRegisterRepo();

  function reset(): void {
    setRepoUrl("");
    setBranch("main");
    setError(null);
  }

  async function submit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    const url = repoUrl.trim();
    if (!url) {
      setError("repo URL required");
      return;
    }
    try {
      await register.mutateAsync({
        repo_url: url,
        default_branch: branch.trim() || "main",
        is_public: true,
      });
      reset();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "register failed");
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 w-[480px] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-background p-6 shadow-xl"
          onEscapeKeyDown={() => onOpenChange(false)}
        >
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="flex items-center gap-2 font-semibold text-[14px]">
              <GitBranch className="size-4" /> Connect a results repo
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
            The server will clone this repo (read-only) and ingest the
            <span className="font-mono"> /ab/runs/</span> directory. Re-scoring
            runs on every sync. Make sure the repo is public.
          </Dialog.Description>

          <form onSubmit={submit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11.5px] text-foreground-2">Repo URL</span>
              <input
                type="text"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/handle/runs-repo"
                className="h-8 px-2 rounded-md border border-border bg-panel-2 text-[12.5px] font-mono"
                autoFocus
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-[11.5px] text-foreground-2">Default branch</span>
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main"
                className="h-8 px-2 rounded-md border border-border bg-panel-2 text-[12.5px] font-mono"
              />
            </label>

            {error && (
              <div className="text-[11.5px] text-fail">{error}</div>
            )}

            <div className="flex justify-end gap-2 mt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={register.isPending}
              >
                {register.isPending ? "Connecting…" : "Connect"}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

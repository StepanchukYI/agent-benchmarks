import { Avatar } from "../ui/Avatar";
import { cn } from "../../lib/utils";
import { operatorByHandle } from "../../lib/mock-data";

interface OperatorTagProps {
  handle: string;
  showRepo?: boolean;
  avatarOnly?: boolean;
  avatarSize?: number;
  className?: string;
}

export function OperatorTag({
  handle,
  showRepo = false,
  avatarOnly = false,
  avatarSize = 16,
  className,
}: OperatorTagProps): JSX.Element | null {
  const op = operatorByHandle(handle);
  if (!op) return null;
  if (avatarOnly) return <Avatar operator={op} size={avatarSize} className={className} />;

  return (
    <span title={op.repo} className={cn("inline-flex items-center gap-1.5", className)}>
      <Avatar operator={op} size={avatarSize} />
      <span
        className={cn(
          "font-mono text-[11.5px]",
          op.is_self ? "text-foreground font-semibold" : "text-foreground-2 font-medium",
        )}
      >
        @{op.handle}
      </span>
      {showRepo && (
        <span className="text-muted-foreground text-[10.5px]">
          · {op.repo.replace("github.com/", "")}
        </span>
      )}
    </span>
  );
}

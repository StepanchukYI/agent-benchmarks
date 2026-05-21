import { Edit, Plus } from "lucide-react";
import { Panel, PanelHeader } from "../ui/Panel";
import { Button } from "../ui/Button";
import { PageHero } from "../shell/PageHero";
import { SCRUBBER_RULES } from "../../lib/mock-data";

export function PrivacyTab(): JSX.Element {
  return (
    <>
      <PageHero
        className="px-0 border-b-0 pt-0"
        title="Privacy"
        subtitle="Scrubber rules applied before any trajectory is published. Once a leak is published, it cannot be unpublished from caches (LSN-006)."
      />

      <Panel>
        <PanelHeader title="Default scrubber rules" actions={<span className="text-[11px] text-muted-foreground">{SCRUBBER_RULES.length} active</span>} />
        <div className="p-3.5 flex flex-col gap-2">
          {SCRUBBER_RULES.map((r) => (
            <div
              key={r.name}
              className="grid items-center gap-2.5 p-2.5 bg-panel-2 rounded-md"
              style={{ gridTemplateColumns: "180px 1fr 1fr 60px" }}
            >
              <span className="text-[12px] font-medium">{r.name}</span>
              <span className="font-mono text-[11px] text-warn break-all">{r.pattern}</span>
              <span className="font-mono text-[11px] text-pass">→ {r.replacement}</span>
              <Button size="icon-sm" variant="ghost"><Edit className="size-3" /></Button>
            </div>
          ))}
          <Button size="sm" className="self-start mt-1.5"><Plus className="size-3" /> Add custom rule</Button>
        </div>
      </Panel>
    </>
  );
}

import { useState } from "react";
import { SubNav } from "../components/shell/SubNav";
import { SettingsSidebar, type SettingsTab } from "../components/settings/SettingsSidebar";
import { AccountTab } from "../components/settings/AccountTab";
import { ReposTab } from "../components/settings/ReposTab";
import { PrivacyTab } from "../components/settings/PrivacyTab";

export default function Settings(): JSX.Element {
  const [tab, setTab] = useState<SettingsTab>("account");

  return (
    <>
      <SubNav crumbs={[{ label: "Settings" }]} />
      <div className="flex flex-1 min-h-0">
        <SettingsSidebar active={tab} onSelect={setTab} />
        <div className="flex-1 min-w-0 overflow-y-auto">
          <div className="p-6 flex flex-col gap-4 max-w-[920px]">
            {tab === "account" && <AccountTab />}
            {tab === "repos" && <ReposTab />}
            {tab === "privacy" && <PrivacyTab />}
            {tab !== "account" && tab !== "repos" && tab !== "privacy" && (
              <div className="rounded-lg border border-border bg-panel p-9 text-center text-muted-foreground">
                <p className="text-[12.5px]">UI not yet implemented — use <span className="font-mono">ab {tab} --help</span></p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

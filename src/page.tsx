import { Tabs } from "@decky/ui";
import { ReactNode, useState } from "react";

import { PageTab, STYLES, takeRequestedTab } from "./common";
import { Loaded, useHexDeck } from "./state";
import { AudioTab } from "./tabs/audio";
import { ControlsTab } from "./tabs/controls";
import { HelpTab } from "./tabs/help";
import { ModelsTab } from "./tabs/models";
import { TextTab } from "./tabs/text";

/** A tab's contents: scrolls on its own, clear of Steam's header and footer. */
function Pane({ children }: { children: ReactNode }) {
  return (
    <div style={{ height: "100%", overflowY: "auto", boxSizing: "border-box", padding: "12px 2.8vw 72px" }}>
      {children}
    </div>
  );
}

/**
 * HexDeck's full-screen page (L1/R1 switch tabs): the model picker and
 * every setting that isn't worth a row in the Quick Access panel.
 */
export function SettingsPage() {
  const loading = useHexDeck();
  const [tab, setTab] = useState<string>(takeRequestedTab());
  if (!loading.state) return null;
  const data = loading as Loaded;

  const tabs: { id: PageTab; title: string; content: ReactNode }[] = [
    { id: "models", title: "Models", content: <ModelsTab data={data} /> },
    { id: "controls", title: "Controls", content: <ControlsTab data={data} /> },
    { id: "text", title: "Text", content: <TextTab data={data} /> },
    { id: "audio", title: "Audio and feedback", content: <AudioTab data={data} /> },
    { id: "help", title: "Help", content: <HelpTab data={data} /> },
  ];

  return (
    <div style={{ marginTop: "40px", height: "calc(100% - 40px)", background: "#0e141b" }}>
      <style>{STYLES}</style>
      <Tabs
        activeTab={tab}
        onShowTab={setTab}
        tabs={tabs.map(({ id, title, content }) => ({ id, title, content: <Pane>{content}</Pane> }))}
      />
    </div>
  );
}

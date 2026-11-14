import { staticClasses } from "@decky/ui";
import { addEventListener, definePlugin, removeEventListener, routerHook } from "@decky/api";

import { HexEvent, bindingLabel } from "./api";
import { PAGE_ROUTE, toast, truncate } from "./common";
import { HexDeckIcon } from "./HexDeckIcon";
import { SettingsPage } from "./page";
import { Panel } from "./panel";

function onHexEvent(event: HexEvent) {
  if (!event.notify && event.kind !== "error") return;
  switch (event.kind) {
    case "recording":
      toast("Listening…");
      break;
    case "done":
      toast(event.text ? truncate(event.text) : "Done");
      if (event.dropped) toast(`${event.dropped} characters couldn't be typed on a US keyboard`);
      break;
    case "nothing":
      toast(event.message || "No speech heard");
      break;
    case "error":
      toast(event.message || "Something went wrong", "HexDeck error");
      break;
    case "installed":
      toast(`Hex ${event.version ?? ""} installed`.replace("  ", " "));
      break;
    case "binding":
      toast(`Binding: ${bindingLabel(event.buttons ?? [])}`);
      break;
    case "model_ready":
      toast(`${event.name ?? "The model"} is ready`);
      break;
  }
}

export default definePlugin(() => {
  const listener = addEventListener<[HexEvent]>("hexdeck_event", onHexEvent);
  routerHook.addRoute(PAGE_ROUTE, SettingsPage, { exact: true });
  return {
    name: "HexDeck",
    titleView: <div className={staticClasses.Title}>HexDeck</div>,
    content: <Panel />,
    icon: <HexDeckIcon />,
    onDismount() {
      removeEventListener("hexdeck_event", listener);
      routerHook.removeRoute(PAGE_ROUTE);
    },
  };
});

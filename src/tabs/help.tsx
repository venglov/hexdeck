import { ButtonItem, DropdownItem, Field } from "@decky/ui";

import { bindingLabel, bytesLabel, installHex, restartHex, takeOverHex } from "../api";
import { toast } from "../common";
import { Loaded } from "../state";
import { describe } from "../status";

/** For when dictation doesn't work: what's running where, and the things to try. */
export function HelpTab({ data }: { data: Loaded }) {
  const { state, models, update, refresh } = data;
  const { config, hex, session, controller, install } = state;
  const status = describe(state, models);

  const run = async (call: () => Promise<{ ok: boolean; error?: string }>, done: string) => {
    const answer = await call();
    toast(answer.ok ? done : answer.error || "That didn't work");
    refresh();
  };

  const hexLine = !hex.installed ? "Not installed"
    : [
      hex.version ? `Version ${hex.version}` : "Unknown version",
      hex.running ? (hex.owned ? "run by HexDeck" : "started outside HexDeck") : "not running",
      hex.running && hex.memory ? `${bytesLabel(hex.memory)} in memory` : null,
      hex.update === "available" ? "update available" : null,
    ].filter(Boolean).join(" · ");

  return (
    <>
      <Field label="Status" description={[status.title, status.detail, state.last_error].filter(Boolean).join(" · ")} />
      <Field
        label="Text doesn't reach the game?"
        description="Try Insert text by → Typing on the Text tab. If Hex was already running when Game Mode started, run it for Game Mode below. As a last resort pick the game display by hand."
      />
      {!hex.installed && install.state !== "running" && (
        <ButtonItem
          label="Install Hex"
          description="Downloads the official Hex build for Linux into ~/.local/bin and checks its signature"
          onClick={() => run(installHex, "Installing Hex…")}
        >
          Install
        </ButtonItem>
      )}
      {hex.installed && session.kind === "gamescope" && hex.external && (
        <ButtonItem
          label="Hex was already running"
          description="HexDeck is using it. Restart it on Game Mode's display so its paste reaches games."
          onClick={() => run(takeOverHex, "Hex now runs for Game Mode")}
        >
          Run Hex for Game Mode
        </ButtonItem>
      )}
      {hex.installed && (
        <ButtonItem label="Restart Hex" description="Stops Hex and starts it again on the game display" onClick={() => run(restartHex, "Hex restarted")}>
          Restart
        </ButtonItem>
      )}
      <DropdownItem
        label="Game display"
        description={`Now ${session.display ?? "none"} (${session.reason})`}
        rgOptions={["auto", ":0", ":1", ":2"].map((display) => ({ data: display, label: display === "auto" ? "Automatic" : display }))}
        selectedOption={config.display}
        onChange={(option) => update("display", option.data)}
      />
      <Field label="Hex" description={hexLine} />
      {hex.path && <Field label="Hex program" description={hex.path} />}
      <Field label="Hex log" description={hex.log} />
      <Field label="Controller" description={controller.device
        ? `${controller.device}${controller.held.length ? ` · holding ${bindingLabel(controller.held)}` : ""}`
        : controller.error || "No controller found"} />
      <Field label="HexDeck" description={`Version ${state.version}`} />
    </>
  );
}

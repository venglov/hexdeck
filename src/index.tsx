import {
  ButtonItem,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  ProgressBarWithInfo,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { addEventListener, definePlugin, removeEventListener, toaster } from "@decky/api";
import { useCallback, useEffect, useRef, useState } from "react";
import { BsHexagonFill } from "react-icons/bs";

import {
  Capture,
  HexEvent,
  HexModel,
  State,
  bindingLabel,
  cancelBindingCapture,
  cancelModelDownload,
  getBindingCapture,
  getHexSettings,
  getState,
  installHex,
  languageName,
  listModels,
  megabytes,
  parseSize,
  restartHex,
  selectModel,
  setConfig,
  setHexSetting,
  startBindingCapture,
  takeOverHex,
  testDictation,
} from "./api";

const toast = (body: string, title = "HexDeck") => toaster.toast({ title, body, duration: 3500 });

const truncate = (text: string, length = 140) => (text.length > length ? `${text.slice(0, length - 1)}…` : text);

function statusLine(state: State): string {
  const { hex, session, install, phase } = state;
  if (install.state === "running") return install.stage;
  if (!hex.installed) return "Hex isn't installed";
  if (phase === "recording" || hex.capture === "recording") return "Recording…";
  if (phase === "transcribing" || hex.capture === "transcribing") return "Transcribing…";
  if (session.kind === "desktop") return hex.running ? "Desktop Mode · using your Hex" : "Desktop Mode · Hex isn't running";
  if (!state.config.enabled) return "Off";
  if (!hex.running) return hex.service_error || "Starting Hex…";
  if (hex.listener === "ModelRequired" || hex.listener.toLowerCase().includes("model")) return "Choose a model to download";
  return hex.listener || "Ready";
}

function BindingRow({ state, refresh }: { state: State; refresh: () => void }) {
  const [capture, setCapture] = useState<Capture | null>(null);
  const timer = useRef<number | null>(null);

  const stopPolling = () => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
  };

  useEffect(() => () => {
    stopPolling();
    cancelBindingCapture();
  }, []);

  const begin = async () => {
    setCapture(await startBindingCapture());
    stopPolling();
    timer.current = window.setInterval(async () => {
      const next = await getBindingCapture();
      setCapture(next);
      if (!next || next.phase === "captured" || next.phase === "cancelled") {
        stopPolling();
        refresh();
        window.setTimeout(() => setCapture(null), 2500);
      }
    }, 150);
  };

  const prompt = (() => {
    if (!capture) return null;
    switch (capture.phase) {
      case "release": return "Let go of every button…";
      case "listening": return "Hold the new button combination";
      case "holding": return `${bindingLabel(capture.buttons)} — let go to save`;
      case "captured": return `Saved: ${bindingLabel(capture.buttons)}`;
      case "cancelled": return capture.error || "Cancelled";
    }
  })();

  const capturing = capture !== null && ["release", "listening", "holding"].includes(capture.phase);
  return (
    <>
      <PanelSectionRow>
        <Field label="Controller binding" description={prompt ?? (state.config.trigger_mode === "hold"
          ? "Hold to record, let go to finish"
          : "Press to record, press again to finish")}>
          {bindingLabel(state.config.binding)}
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={capturing ? () => cancelBindingCapture() : begin}>
          {capturing ? "Cancel" : "Change binding"}
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}

function ModelSection({ state, models, reloadModels }: { state: State; models: HexModel[]; reloadModels: () => void }) {
  const selected = models.find((model) => model.selected) ?? models.find((model) => model.id === state.hex.model.id);
  const preparing = state.hex.model.preparing;
  const preparingModel = models.find((model) => model.id === preparing || model.name === preparing);
  const total = preparingModel ? parseSize(preparingModel.size) : null;
  const received = state.hex.model.downloaded_bytes ?? 0;

  const choose = async (id: string, language: string) => {
    const answer = await selectModel(id, language);
    if (!answer.ok) toast(answer.error ?? "Couldn't change the model");
    else if (answer.downloading) toast("Downloading the model. Dictation starts when it's ready.");
    reloadModels();
  };

  if (!state.hex.running) {
    return (
      <PanelSection title="Speech model">
        <PanelSectionRow>
          <Field label="Model" description="Available once Hex is running">{state.hex.model.name || "—"}</Field>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <PanelSection title="Speech model">
      <PanelSectionRow>
        <DropdownItem
          label="Model"
          description={selected ? `${selected.size}${selected.installed ? "" : " · not downloaded"}` : undefined}
          menuLabel="Hex speech model"
          rgOptions={models.map((model) => ({
            data: model.id,
            label: model.installed ? model.name : `${model.name} (download ${model.size})`,
          }))}
          selectedOption={selected?.id}
          strDefaultLabel="Choose a model"
          onChange={(option) => choose(option.data, "")}
        />
      </PanelSectionRow>
      {selected && selected.languages.length > 1 && (
        <PanelSectionRow>
          <DropdownItem
            label="Language"
            menuLabel="Dictation language"
            rgOptions={selected.languages.map((code) => ({ data: code, label: languageName(code) }))}
            selectedOption={state.hex.model.language}
            onChange={(option) => choose(selected.id, option.data)}
          />
        </PanelSectionRow>
      )}
      {preparing && (
        <>
          <PanelSectionRow>
            <ProgressBarWithInfo
              label={`Preparing ${preparingModel?.name ?? preparing}`}
              nProgress={total ? Math.min(100, (received / total) * 100) : undefined}
              indeterminate={!total}
              sOperationText={total ? `${megabytes(received)} of ${preparingModel?.size}` : megabytes(received)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={async () => { await cancelModelDownload(); reloadModels(); }}>
              Cancel download
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {state.hex.model.error && (
        <PanelSectionRow>
          <Field label="Model error" description={state.hex.model.error} />
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

function Content() {
  const [state, setState] = useState<State | null>(null);
  const [models, setModels] = useState<HexModel[]>([]);
  const [hexSettings, setHexSettings] = useState<Record<string, unknown>>({});
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const running = state?.hex.running ?? false;

  const refresh = useCallback(async () => {
    try {
      setState(await getState());
    } catch (error) {
      console.error("HexDeck: get_state failed", error);
    }
  }, []);

  const reloadModels = useCallback(async () => {
    const answer = await listModels();
    if (answer.ok) setModels(answer.models);
    const settings = await getHexSettings();
    if (settings.ok) setHexSettings(settings.settings);
    refresh();
  }, [refresh]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // Models and Hex's settings come from the running Hex.
  useEffect(() => {
    if (running) reloadModels();
  }, [running, reloadModels]);

  // A finished download changes what's installed.
  const preparing = state?.hex.model.preparing ?? null;
  const wasPreparing = useRef<string | null>(null);
  useEffect(() => {
    if (wasPreparing.current && !preparing) reloadModels();
    wasPreparing.current = preparing;
  }, [preparing, reloadModels]);

  if (!state) {
    return (
      <PanelSection>
        <PanelSectionRow><Field label="Loading…" /></PanelSectionRow>
      </PanelSection>
    );
  }

  const update = async (key: string, value: unknown) => {
    const answer = await setConfig(key, value);
    if (!answer.ok) toast(answer.error ?? `Couldn't save ${key}`);
    refresh();
  };

  const updateHex = async (key: string, value: string) => {
    const answer = await setHexSetting(key, value);
    if (!answer.ok) toast(answer.error ?? `Hex didn't accept ${key}`);
    reloadModels();
  };

  const { config, hex, install, session } = state;
  const hotkey = typeof hexSettings.dictation_hotkey === "string" ? hexSettings.dictation_hotkey : undefined;
  const shortcutOptions = [...state.keyboard_shortcuts];
  if (hotkey && !shortcutOptions.some((option) => option.value === hotkey)) {
    shortcutOptions.push({ value: hotkey, label: hotkey });
  }

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    const answer = await testDictation(4);
    setTesting(false);
    setTestResult(answer.ok ? (answer.text ? `“${answer.text}”` : "No speech heard") : answer.error ?? "Test failed");
  };

  return (
    <>
      <PanelSection>
        <PanelSectionRow>
          <ToggleField
            label="Enable"
            description={statusLine(state)}
            checked={config.enabled}
            onChange={(value) => update("enabled", value)}
          />
        </PanelSectionRow>

        {!hex.installed && (
          <>
            <PanelSectionRow>
              <Field
                label="Install Hex"
                description="Downloads the official Hex build for Linux into ~/.local/bin and checks its signature."
              />
            </PanelSectionRow>
            {install.state === "running" ? (
              <PanelSectionRow>
                <ProgressBarWithInfo
                  label={install.stage}
                  nProgress={install.total ? (install.received / install.total) * 100 : undefined}
                  indeterminate={!install.total}
                  sOperationText={install.total ? `${megabytes(install.received)} of ${megabytes(install.total)}` : undefined}
                />
              </PanelSectionRow>
            ) : (
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={async () => {
                  const answer = await installHex();
                  if (!answer.ok) toast(answer.error ?? "Couldn't start the install");
                  refresh();
                }}>
                  Install Hex
                </ButtonItem>
              </PanelSectionRow>
            )}
            {install.state === "failed" && (
              <PanelSectionRow><Field label="Install failed" description={install.error} /></PanelSectionRow>
            )}
          </>
        )}

        {hex.installed && session.kind === "gamescope" && hex.external && (
          <>
            <PanelSectionRow>
              <Field
                label="Hex was already running"
                description="HexDeck is using it. If dictation doesn't reach your game, run Hex on Game Mode's display instead."
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={async () => {
                const answer = await takeOverHex();
                if (!answer.ok) toast(answer.error ?? "Couldn't restart Hex");
                refresh();
              }}>
                Run Hex for Game Mode
              </ButtonItem>
            </PanelSectionRow>
          </>
        )}

        {state.last_text && (
          <PanelSectionRow>
            <Field label="Last dictation" description={truncate(state.last_text)} />
          </PanelSectionRow>
        )}
        {state.last_error && (
          <PanelSectionRow>
            <Field label="Last error" description={state.last_error} />
          </PanelSectionRow>
        )}
      </PanelSection>

      <ModelSection state={state} models={models} reloadModels={reloadModels} />

      <PanelSection title="Dictation controls">
        <BindingRow state={state} refresh={refresh} />
        <PanelSectionRow>
          <DropdownItem
            label="Trigger"
            rgOptions={[
              { data: "hold", label: "Hold to talk" },
              { data: "toggle", label: "Press to start and stop" },
            ]}
            selectedOption={config.trigger_mode}
            onChange={(option) => update("trigger_mode", option.data)}
          />
        </PanelSectionRow>
        {running && (
          <PanelSectionRow>
            <DropdownItem
              label="Keyboard shortcut"
              description="Hex's own shortcut, for a USB or Bluetooth keyboard"
              rgOptions={shortcutOptions.map((option) => ({ data: option.value, label: option.label }))}
              selectedOption={hotkey}
              strDefaultLabel="—"
              onChange={(option) => updateHex("dictation_hotkey", option.data)}
            />
          </PanelSectionRow>
        )}
        {running && (
          <>
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={testing} onClick={runTest}>
                {testing ? "Listening for 4 seconds…" : "Test dictation"}
              </ButtonItem>
            </PanelSectionRow>
            {testResult !== null && (
              <PanelSectionRow><Field label="Heard" description={testResult} /></PanelSectionRow>
            )}
          </>
        )}
      </PanelSection>

      <PanelSection title="Text output">
        <PanelSectionRow>
          <DropdownItem
            label="Insert text by"
            description={config.output === "paste"
              ? "Hex pastes the text, in any language"
              : "Types on a virtual US keyboard, for games that ignore paste"}
            rgOptions={[
              { data: "paste", label: "Pasting (Hex)" },
              { data: "type", label: "Typing (US keyboard)" },
            ]}
            selectedOption={config.output}
            onChange={(option) => update("output", option.data)}
          />
        </PanelSectionRow>
        {config.output === "type" && (
          <PanelSectionRow>
            <ToggleField
              label="Press Enter after typing"
              description="Sends a chat message straight away"
              checked={config.press_enter}
              onChange={(value) => update("press_enter", value)}
            />
          </PanelSectionRow>
        )}
        {running && typeof hexSettings.sound_effects === "boolean" && (
          <PanelSectionRow>
            <ToggleField
              label="Hex sounds"
              description="Tones when recording starts and stops"
              checked={hexSettings.sound_effects}
              onChange={(value) => updateHex("sound_effects", value ? "on" : "off")}
            />
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ToggleField
            label="Notifications"
            description="Steam toasts when recording starts and with the result"
            checked={config.notifications}
            onChange={(value) => update("notifications", value)}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Advanced">
        <PanelSectionRow>
          <ToggleField label="Show advanced settings" checked={advanced} onChange={setAdvanced} />
        </PanelSectionRow>
        {advanced && (
          <>
            <PanelSectionRow>
              <ToggleField
                label="Hide Hex's recording pill"
                description="While HexDeck runs Hex in Game Mode; restored afterwards"
                checked={config.hide_hex_pill}
                onChange={(value) => update("hide_hex_pill", value)}
              />
            </PanelSectionRow>
            {config.trigger_mode === "hold" && (
              <PanelSectionRow>
                <DropdownItem
                  label="Ignore taps shorter than"
                  rgOptions={[0, 200, 300, 500, 800].map((ms) => ({ data: ms, label: ms ? `${ms} ms` : "Off" }))}
                  selectedOption={config.min_hold_ms}
                  onChange={(option) => update("min_hold_ms", option.data)}
                />
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <DropdownItem
                label="Game display"
                description={`Now ${session.display ?? "none"} (${session.reason})`}
                rgOptions={["auto", ":0", ":1", ":2"].map((display) => ({ data: display, label: display === "auto" ? "Automatic" : display }))}
                selectedOption={config.display}
                onChange={(option) => update("display", option.data)}
              />
            </PanelSectionRow>
            {hex.installed && (
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={async () => {
                  const answer = await restartHex();
                  toast(answer.ok ? "Hex restarted" : answer.error || "Hex didn't come back");
                  refresh();
                }}>
                  Restart Hex
                </ButtonItem>
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <Field label="Controller" description={state.controller.device
                ? `${state.controller.device}${state.controller.held.length ? ` · holding ${bindingLabel(state.controller.held)}` : ""}`
                : state.controller.error} />
            </PanelSectionRow>
            <PanelSectionRow>
              <Field label="Hex" description={hex.installed
                ? `${hex.version ?? "unknown version"} · ${hex.path}${hex.owned ? " · run by HexDeck" : ""}`
                : "Not installed"} />
            </PanelSectionRow>
            <PanelSectionRow>
              <Field label="Hex log" description={hex.log} />
            </PanelSectionRow>
            <PanelSectionRow>
              <Field label="HexDeck" description={`Version ${state.version}`} />
            </PanelSectionRow>
          </>
        )}
      </PanelSection>
    </>
  );
}

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
  }
}

export default definePlugin(() => {
  const listener = addEventListener<[HexEvent]>("hexdeck_event", onHexEvent);
  return {
    name: "HexDeck",
    titleView: <div className={staticClasses.Title}>HexDeck</div>,
    content: <Content />,
    icon: <BsHexagonFill />,
    onDismount() {
      removeEventListener("hexdeck_event", listener);
    },
  };
});

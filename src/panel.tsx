import { ButtonItem, DialogButton, DropdownItem, Field, Focusable, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { useState } from "react";

import {
  HexModel,
  bytesLabel,
  installHex,
  languageName,
  languageSummary,
  pasteLast,
  restartHex,
  takeOverHex,
  testDictation,
} from "./api";
import { Bar, COLORS, Keys, STYLES, openPage, toast, truncate } from "./common";
import { Loaded, useHexDeck } from "./state";
import { Status, Tone, describe } from "./status";

const TONE_COLORS: Record<Tone, string> = {
  ok: COLORS.ok, recording: COLORS.recording, busy: COLORS.accent, off: COLORS.muted, warn: COLORS.warn, setup: COLORS.accent,
};

const BROWSE = "__browse__";

const SETUP_STEPS = ["Install Hex", "Pick a model for your language", "Try it"];

/**
 * The card at the top of the panel: what dictation is doing, what to press,
 * what it heard last, and, when something is in the way, the one button
 * that fixes it.
 */
function StatusCard({ data, status }: { data: Loaded; status: Status }) {
  const { state, refresh } = data;
  const binding = <Keys buttons={state.config.binding} />;
  const hold = state.config.trigger_mode === "hold";
  const instruction = status.instruction === "recording"
    ? (hold ? <>Let go of {binding} to finish</> : <>Press {binding} again to finish</>)
    : status.instruction === "ready"
      ? (hold ? <>Hold {binding} and speak</> : <>Press {binding}, speak, press again</>)
      : null;

  const act = async () => {
    if (status.action === "models") return openPage("models");
    const answer = status.action === "install" ? await installHex()
      : status.action === "takeover" ? await takeOverHex()
        : await restartHex();
    if (!answer.ok) toast(answer.error || "That didn't work");
    else if (status.action === "restart") toast("Hex restarted");
    refresh();
  };
  const actionLabel = { install: "Install Hex", models: "Choose a model", takeover: "Run Hex for Game Mode", restart: "Restart Hex" };

  return (
    <>
      <PanelSectionRow>
        <div className="hexdeck-card" style={{ padding: "10px 12px", margin: "2px 0 6px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 600, fontSize: "15px" }}>
            <span style={{
              width: "9px", height: "9px", borderRadius: "50%", flex: "none", background: TONE_COLORS[status.tone],
              animation: status.tone === "recording" ? "hexdeck-pulse 1s ease-in-out infinite" : undefined,
            }} />
            {status.title}
          </div>
          {status.step && (
            <div style={{ marginTop: "6px", fontSize: "12px" }}>
              {SETUP_STEPS.map((step, index) => (
                <div key={step} style={{ color: index + 1 === status.step ? undefined : COLORS.muted }}>
                  {index + 1 < status.step! ? "✓" : `${index + 1}.`} {step}
                </div>
              ))}
            </div>
          )}
          {instruction && <div style={{ marginTop: "6px", fontSize: "13px" }}>{instruction}</div>}
          {status.progress !== undefined && <Bar progress={status.progress ?? undefined} />}
          {status.detail && <div style={{ marginTop: "4px", fontSize: "12px", color: COLORS.muted }}>{status.detail}</div>}
          {status.tone === "ok" && state.last_error && (
            <div style={{ marginTop: "6px", fontSize: "12px", color: COLORS.warn }}>{state.last_error}</div>
          )}
          {status.tone === "ok" && !state.last_error && state.last_text && (
            <div style={{ marginTop: "6px", fontSize: "12px", color: COLORS.muted, fontStyle: "italic" }}>
              “{truncate(state.last_text, 110)}”
            </div>
          )}
        </div>
      </PanelSectionRow>
      {status.action && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={act}>{actionLabel[status.action]}</ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}

/** What the model in use does about language: a setting, or a line saying it needs none. */
function LanguageRow({ data, model }: { data: Loaded; model: HexModel }) {
  if (model.language_mode !== "choice") {
    return (
      <PanelSectionRow>
        <Field label="Language" description={model.language_mode === "automatic"
          ? `${model.name} hears which of its ${languageSummary(model)} you speak`
          : `${model.name} knows ${languageSummary(model)}`} />
      </PanelSectionRow>
    );
  }
  const current = model.language_choices.includes(data.saved) ? data.saved : undefined;
  return (
    <PanelSectionRow>
      <DropdownItem
        label="Language"
        menuLabel="Dictation language"
        rgOptions={model.language_choices.map((code) => ({
          data: code,
          label: code === "auto" ? "Automatic (detect)" : languageName(code),
        }))}
        selectedOption={current}
        strDefaultLabel={data.saved ? languageName(data.saved) : "—"}
        onChange={(option) => data.setSpeak(option.data)}
      />
    </PanelSectionRow>
  );
}

/**
 * The Quick Access panel: the state at a glance and the few things that
 * change mid-game. Everything else is on the full-screen page.
 */
export function Panel() {
  const loading = useHexDeck();
  const [testing, setTesting] = useState(false);
  const [heard, setHeard] = useState<string | null>(null);

  if (!loading.state) {
    return (
      <PanelSection>
        <PanelSectionRow><Field label="Loading…" /></PanelSectionRow>
      </PanelSection>
    );
  }
  const data = loading as Loaded;
  const { state, models, selected, preparing, update, choose } = data;
  const { config, hex, session } = state;
  const status = describe(state, models);
  const downloaded = models.filter((model) => model.installed || model.selected);
  const memory = hex.running && hex.owned && hex.memory ? ` and frees ${bytesLabel(hex.memory)}` : "";

  const runTest = async () => {
    setTesting(true);
    setHeard(null);
    const answer = await testDictation(4);
    setTesting(false);
    setHeard(answer.ok ? (answer.text ? `“${answer.text}”` : "No speech heard") : answer.error ?? "Test failed");
  };

  const again = async () => {
    const answer = await pasteLast();
    if (!answer.ok) toast(answer.error ?? "Couldn't insert the text again");
  };

  return (
    <>
      <style>{STYLES}</style>
      <PanelSection>
        <StatusCard data={data} status={status} />
        {hex.installed && (
          <PanelSectionRow>
            <ToggleField
              label="Dictation"
              description={session.kind === "desktop"
                ? "Whether the controller binding dictates"
                : config.enabled ? `Off stops Hex${memory}` : "On starts Hex for Game Mode"}
              checked={config.enabled}
              onChange={(value) => update("enabled", value)}
            />
          </PanelSectionRow>
        )}
      </PanelSection>

      {hex.running && status.step !== 2 && (
        <PanelSection title="Speech">
          <PanelSectionRow>
            <DropdownItem
              label="Model"
              menuLabel="Downloaded models"
              disabled={!!preparing}
              description={selected ? [selected.wait, languageSummary(selected)].filter(Boolean).join(" · ") : "None chosen yet"}
              rgOptions={[
                ...downloaded.map((model) => ({ data: model.id, label: model.name })),
                { data: BROWSE, label: "Browse all models…" },
              ]}
              selectedOption={selected?.id}
              strDefaultLabel="Choose…"
              onChange={(option) => {
                if (option.data === BROWSE) return openPage("models");
                const model = models.find((candidate) => candidate.id === option.data);
                if (model && !model.selected) choose(model);
              }}
            />
          </PanelSectionRow>
          {selected && <LanguageRow data={data} model={selected} />}
        </PanelSection>
      )}

      {hex.installed && (
        <PanelSection title="Text">
          <PanelSectionRow>
            <DropdownItem
              label="Insert text by"
              description={config.output === "paste" ? "Any language" : "For games that ignore paste"}
              rgOptions={[
                { data: "paste", label: "Pasting" },
                { data: "type", label: "Typing" },
              ]}
              selectedOption={config.output}
              onChange={(option) => update("output", option.data)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              label="Press Enter after"
              description="Sends a chat message straight away"
              checked={config.press_enter}
              onChange={(value) => update("press_enter", value)}
            />
          </PanelSectionRow>
          {hex.running && status.step !== 2 && (
            <PanelSectionRow>
              <Focusable flow-children="horizontal" style={{ display: "flex", gap: "8px", padding: "8px 0" }}>
                <DialogButton style={{ minWidth: 0, flex: 1, padding: "8px 4px" }} disabled={testing} onClick={runTest}>
                  {testing ? "Speak now…" : "Try it"}
                </DialogButton>
                <DialogButton style={{ minWidth: 0, flex: 1, padding: "8px 4px" }} disabled={config.output === "type" && !state.last_text} onClick={again}>
                  Paste again
                </DialogButton>
              </Focusable>
            </PanelSectionRow>
          )}
          {heard !== null && (
            <PanelSectionRow><Field label="Heard in 4 seconds" description={heard} /></PanelSectionRow>
          )}
        </PanelSection>
      )}

      <PanelSection>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => openPage()}>
            All settings
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

import { ButtonItem, DropdownItem, Field } from "@decky/ui";
import { useEffect, useRef, useState } from "react";

import { Capture, bindingLabel, cancelBindingCapture, getBindingCapture, startBindingCapture } from "../api";
import { Keys } from "../common";
import { Loaded } from "../state";

/** Bindings on the back grips, which games rarely use; anything else is captured. */
const PRESETS: string[][] = [["L4", "R4"], ["L5", "R5"], ["L4", "L5"], ["R4", "R5"], ["L4"], ["R4"], ["L5"], ["R5"]];
const same = (a: string[], b: string[]) => a.length === b.length && a.every((button) => b.includes(button));

/** Record a new binding by holding it. */
function useBindingCapture(refresh: () => void) {
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
      case "listening": return "Hold the buttons you want, up to four";
      case "holding": return `${bindingLabel(capture.buttons)} — let go to save`;
      case "captured": return `Saved: ${bindingLabel(capture.buttons)}`;
      case "cancelled": return capture.error || "Cancelled";
    }
  })();
  const capturing = capture !== null && ["release", "listening", "holding"].includes(capture.phase);
  return { begin, prompt, capturing };
}

/** How dictation is triggered: the controller binding, hold or toggle, and Hex's keyboard shortcut. */
export function ControlsTab({ data }: { data: Loaded }) {
  const { state, hexSettings, update, updateHex, refresh } = data;
  const { config, controller } = state;
  const { begin, prompt, capturing } = useBindingCapture(refresh);

  const preset = PRESETS.findIndex((buttons) => same(buttons, config.binding));
  const hotkey = typeof hexSettings.dictation_hotkey === "string" ? hexSettings.dictation_hotkey : undefined;
  const shortcuts = [...state.keyboard_shortcuts];
  if (hotkey && !shortcuts.some((option) => option.value === hotkey)) shortcuts.push({ value: hotkey, label: hotkey });

  return (
    <>
      <DropdownItem
        label="Controller binding"
        description="The back grips are the safe choice: games still see every button you hold"
        rgOptions={[
          ...PRESETS.map((buttons, index) => ({ data: index, label: bindingLabel(buttons) })),
          ...(preset < 0 ? [{ data: -1, label: `Custom: ${bindingLabel(config.binding)}` }] : []),
        ]}
        selectedOption={preset}
        onChange={(option) => { if (option.data >= 0) update("binding", PRESETS[option.data]); }}
      />
      <ButtonItem
        label="Any other buttons"
        description={prompt ?? "Hold one to four buttons together, then let go"}
        onClick={capturing ? () => cancelBindingCapture() : begin}
      >
        {capturing ? "Cancel" : "Record a binding"}
      </ButtonItem>
      <Field
        label="Held right now"
        description={controller.device ? "Press the binding to check the Deck reads it" : controller.error || "No controller found"}
      >
        {controller.held.length ? <Keys buttons={controller.held} /> : "—"}
      </Field>
      <DropdownItem
        label="Trigger"
        description={config.trigger_mode === "hold" ? "Hold to record, let go to finish" : "Press to record, press again to finish"}
        rgOptions={[
          { data: "hold", label: "Hold to talk" },
          { data: "toggle", label: "Press to start and stop" },
        ]}
        selectedOption={config.trigger_mode}
        onChange={(option) => update("trigger_mode", option.data)}
      />
      {config.trigger_mode === "hold" && (
        <DropdownItem
          label="Ignore taps shorter than"
          description="A brush against the grips won't start a dictation"
          rgOptions={[0, 200, 300, 500, 800].map((ms) => ({ data: ms, label: ms ? `${ms} ms` : "Off" }))}
          selectedOption={config.min_hold_ms}
          onChange={(option) => update("min_hold_ms", option.data)}
        />
      )}
      {state.hex.running && (
        <DropdownItem
          label="Keyboard shortcut"
          description="Hex's own shortcut, for a USB or Bluetooth keyboard"
          rgOptions={shortcuts.map((option) => ({ data: option.value, label: option.label }))}
          selectedOption={hotkey}
          strDefaultLabel="—"
          onChange={(option) => updateHex("dictation_hotkey", option.data)}
        />
      )}
    </>
  );
}

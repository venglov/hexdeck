import { DropdownItem, Field, ToggleField } from "@decky/ui";

import { Choice } from "../api";
import { Loaded } from "../state";

/** Friendlier names for values Hex lists by their setting spelling. */
const LABELS: Record<string, string> = {
  "system-default": "System default",
  none: "System default",
  nothing: "Leave it alone",
  do_nothing: "Leave it alone",
  off: "Leave it alone",
  mute: "Mute it",
  pause: "Pause media",
  duck: "Lower it",
};

const options = (choices: Choice[]) =>
  choices.map((choice) => ({ data: choice.value, label: choice.label !== choice.value ? choice.label : LABELS[choice.value] ?? choice.label }));

/**
 * What goes in and how you know it's working: the microphone, what happens
 * to game audio while recording, Hex's tones and pill, and Steam's toasts.
 * Hex's own settings appear only when the running Hex lists them.
 */
export function AudioTab({ data }: { data: Loaded }) {
  const { state, hexSettings, hexChoices, update, updateHex } = data;
  const { config, hex } = state;
  const onOff = (value: boolean) => (value ? "on" : "off");
  const text = (key: string) => (typeof hexSettings[key] === "string" ? (hexSettings[key] as string) : undefined);

  return (
    <>
      {!hex.running && (
        <Field label="Hex's sound settings" description="Available once Hex is running" />
      )}
      {hex.running && hexChoices.microphone && (
        <DropdownItem
          label="Microphone"
          description="A headset keeps fan and button noise out of what Hex hears"
          rgOptions={options(hexChoices.microphone)}
          selectedOption={text("microphone") ?? "system-default"}
          strDefaultLabel={text("microphone") ?? "System default"}
          onChange={(option) => updateHex("microphone", option.data)}
        />
      )}
      {hex.running && typeof hexSettings.avoid_bluetooth_microphone === "boolean" && (
        <ToggleField
          label="Avoid Bluetooth microphones"
          description="With System default, records from the built-in microphone so a Bluetooth headset keeps its sound quality"
          checked={hexSettings.avoid_bluetooth_microphone}
          onChange={(value) => updateHex("avoid_bluetooth_microphone", onOff(value))}
        />
      )}
      {hex.running && hexChoices.recording_audio_behavior && (
        <DropdownItem
          label="Game audio while recording"
          description="Lowering it keeps the speakers out of the microphone"
          rgOptions={options(hexChoices.recording_audio_behavior)}
          selectedOption={text("recording_audio_behavior")}
          strDefaultLabel={text("recording_audio_behavior") ?? "—"}
          onChange={(option) => updateHex("recording_audio_behavior", option.data)}
        />
      )}
      {hex.running && typeof hexSettings.sound_effects === "boolean" && (
        <ToggleField
          label="Hex sounds"
          description="Tones when recording starts and stops"
          checked={hexSettings.sound_effects}
          onChange={(value) => updateHex("sound_effects", onOff(value))}
        />
      )}
      <ToggleField
        label="Notifications"
        description="Steam toasts when recording starts and with the result. Errors always show."
        checked={config.notifications}
        onChange={(value) => update("notifications", value)}
      />
      <ToggleField
        label="Show Hex's recording pill"
        description="Hex's own on-screen indicator. HexDeck hides it in Game Mode by default and puts it back afterwards."
        checked={!config.hide_hex_pill}
        onChange={(value) => update("hide_hex_pill", !value)}
      />
    </>
  );
}

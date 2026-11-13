import { callable } from "@decky/api";

export type Answer = { ok: boolean; error?: string; message?: string; [key: string]: unknown };

export type Config = {
  enabled: boolean;
  binding: string[];
  trigger_mode: "hold" | "toggle";
  output: "paste" | "type";
  press_enter: boolean;
  min_hold_ms: number;
  display: string;
  hide_hex_pill: boolean;
  notifications: boolean;
  hex_path: string;
};

export type HexModelReport = {
  id?: string;
  name?: string;
  language?: string;
  installed?: boolean;
  preparing?: string | null;
  downloaded_bytes?: number;
  error?: string | null;
};

export type State = {
  version: string;
  config: Config;
  session: { kind: "gamescope" | "desktop"; display: string | null; reason: string };
  hex: {
    installed: boolean;
    path: string | null;
    version: string | null;
    running: boolean;
    owned: boolean;
    external: boolean;
    service_error: string;
    listener: string;
    capture: string;
    model: HexModelReport;
    log: string;
  };
  controller: { device: string | null; error: string; held: string[] };
  install: { state: "idle" | "running" | "done" | "failed"; stage: string; error: string; version: string; received: number; total: number };
  phase: "idle" | "recording" | "transcribing";
  last_text: string;
  last_error: string;
  keyboard_shortcuts: { value: string; label: string }[];
};

export type HexModel = {
  id: string;
  name: string;
  languages: string[];
  size: string;
  installed: boolean;
  selected: boolean;
  streams?: boolean;
  /** download | hex | imported | found: owner/name@rev */
  source?: string;
  /** automatic: the model hears the language itself and has no setting;
   *  choice: the language goes to the model ("auto" where it detects);
   *  fixed: one language. Added by HexDeck's backend (languages.py). */
  language_mode: "automatic" | "choice" | "fixed";
  detects_language: boolean | null;
  language_choices: string[];
};

export type Capture = { phase: "release" | "listening" | "holding" | "captured" | "cancelled"; buttons: string[]; error: string };

export type HexEvent = {
  kind: "recording" | "transcribing" | "done" | "nothing" | "cancelled" | "error" | "installed" | "binding";
  notify: boolean;
  message?: string;
  text?: string;
  dropped?: number;
  version?: string;
  buttons?: string[];
};

export const getState = callable<[], State>("get_state");
export const setConfig = callable<[key: string, value: unknown], Answer>("set_config");
export const listModels = callable<[], Answer & { models: HexModel[] }>("list_models");
export const selectModel = callable<[modelId: string, language: string], Answer & { downloading?: boolean }>("select_model");
export const removeModel = callable<[modelId: string], Answer>("remove_model");
export const cancelModelDownload = callable<[], Answer>("cancel_model_download");
export const getHexSettings = callable<[], Answer & { settings: Record<string, unknown> }>("get_hex_settings");
export const setHexSetting = callable<[key: string, value: string], Answer>("set_hex_setting");
export const installHex = callable<[], Answer>("install_hex");
export const takeOverHex = callable<[], Answer>("take_over_hex");
export const restartHex = callable<[], Answer>("restart_hex");
export const testDictation = callable<[seconds: number], Answer & { text?: string }>("test_dictation");
export const startBindingCapture = callable<[], Capture>("start_binding_capture");
export const getBindingCapture = callable<[], Capture | null>("get_binding_capture");
export const cancelBindingCapture = callable<[], void>("cancel_binding_capture");

export const bindingLabel = (buttons: string[]) => (buttons.length ? buttons.join(" + ") : "None");

export const megabytes = (bytes: number) => `${(bytes / 1048576).toFixed(0)} MB`;


/** A short note on the model's languages for its description. */
export const languageSummary = (model: HexModel): string => {
  if (model.languages.includes("*")) return "any language";
  const count = model.languages.filter((code) => code !== "auto").length;
  if (count === 1) return `${languageName(model.languages[0])} only`;
  return `${count} languages`;
};

export const percent = (part: number, whole: number) => Math.min(100, Math.max(0, (part / whole) * 100));

/** "478 MB" / "1.6 GB" -> bytes, for a download progress bar. */
export const parseSize = (size: string): number | null => {
  const match = /([\d.]+)\s*(KB|MB|GB)/i.exec(size || "");
  if (!match) return null;
  const unit = { KB: 1e3, MB: 1e6, GB: 1e9 }[match[2].toUpperCase() as "KB" | "MB" | "GB"];
  return parseFloat(match[1]) * unit;
};

/** Hex's language codes, shown with a readable name where the browser knows it. */
export const languageName = (code: string): string => {
  if (code === "auto") return "Automatic";
  try {
    const names = new Intl.DisplayNames(["en"], { type: "language" });
    return names.of(code) || code;
  } catch {
    return code;
  }
};

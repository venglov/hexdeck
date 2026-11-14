import { useCallback, useEffect, useRef, useState } from "react";

import {
  Choice,
  HexModel,
  Role,
  State,
  getHexSettings,
  getState,
  listModels,
  selectModel,
  setConfig,
  setHexSetting,
} from "./api";
import { toast } from "./common";

/** Hex's picks per language, best first, from list_models. */
export type Guide = Record<string, [string, Role][]>;

export const isPreparing = (model: HexModel, preparing: string | null | undefined) =>
  !!preparing && (preparing === model.id || preparing === model.name);

/** The language to hand a model: the one you speak, where the model takes it. */
export const languageFor = (model: HexModel, speak: string) =>
  model.language_mode === "choice" && model.language_choices.includes(speak) ? speak : "";

/** Whether a model understands `speak` ("auto": it detects the language itself). */
export const understands = (model: HexModel, speak: string) =>
  speak === "auto"
    ? model.language_mode === "automatic" || model.language_choices.includes("auto")
    : (model.supported_languages ?? model.languages).includes(speak);

/**
 * Everything the panel and the settings page show: HexDeck's state (polled
 * every second), Hex's models and settings (reloaded when Hex starts and
 * when a download ends), and the calls that change them.
 */
export function useHexDeck() {
  const [state, setState] = useState<State | null>(null);
  const [models, setModels] = useState<HexModel[]>([]);
  const [guide, setGuide] = useState<Guide>({});
  const [diskFree, setDiskFree] = useState<number | null>(null);
  const [hexSettings, setHexSettings] = useState<Record<string, unknown>>({});
  const [hexChoices, setHexChoices] = useState<Record<string, Choice[]>>({});
  const running = state?.hex.running ?? false;

  const refresh = useCallback(async () => {
    try {
      setState(await getState());
    } catch (error) {
      console.error("HexDeck: get_state failed", error);
    }
  }, []);

  const reloadModels = useCallback(async () => {
    try {
      const answer = await listModels();
      if (answer.ok) {
        setModels(answer.models);
        setGuide(answer.recommendations ?? {});
        setDiskFree(answer.disk_free ?? null);
      }
      const settings = await getHexSettings();
      if (settings.ok) {
        setHexSettings(settings.settings);
        setHexChoices(settings.choices ?? {});
      }
    } catch (error) {
      console.error("HexDeck: loading Hex's models failed", error);
    }
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

  const selected = models.find((model) => model.selected) ?? models.find((model) => model.id === state?.hex.model.id);
  const saved = state?.hex.model.language ?? "";
  // Until you say what you speak, go by the language Hex has saved.
  const speak = state?.config.speak_language || (guide[saved] ? saved : "auto");

  const use = async (model: HexModel, language: string) => {
    const answer = await selectModel(model.id, language);
    if (!answer.ok) toast(answer.error ?? "Couldn't change the model");
    else if (answer.downloading) toast(`Downloading ${model.name}. You'll get a notification when it's ready.`);
    reloadModels();
  };

  /** Use a model (downloading it first if needed), in the language you speak. */
  const choose = (model: HexModel) => use(model, languageFor(model, speak));

  /** Say what you speak; the model in use hears about it if it takes a language. */
  const setSpeak = async (code: string) => {
    await update("speak_language", code);
    if (selected && languageFor(selected, code) && saved !== code) await use(selected, code);
  };

  return {
    state, models, guide, diskFree, hexSettings, hexChoices, selected, saved, speak, preparing,
    refresh, reloadModels, update, updateHex, choose, setSpeak,
  };
}

export type HexDeckData = ReturnType<typeof useHexDeck>;
/** The same, once the first state has arrived. */
export type Loaded = HexDeckData & { state: State };

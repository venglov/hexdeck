import { HexModel, State, megabytes, parseSize, percent } from "./api";
import { isPreparing } from "./state";

export type Tone = "ok" | "recording" | "busy" | "off" | "warn" | "setup";

/** What the fix is, when there is one thing to do next. */
export type StatusAction = "install" | "models" | "takeover" | "restart";

export type Status = {
  tone: Tone;
  title: string;
  /** One line under the title; `instruction` replaces it with "Hold L4 + R4 and speak". */
  detail?: string;
  instruction?: "ready" | "recording";
  /** A bar: a percentage, or null when the total isn't known. */
  progress?: number | null;
  action?: StatusAction;
  /** Setup step 1 to 3 (install Hex, pick a model, try it) while setting up. */
  step?: 1 | 2;
};

const needsModel = (state: State) => {
  const listener = state.hex.listener.toLowerCase();
  return listener.includes("model") || listener.includes("setup") || state.hex.model.installed === false;
};

/**
 * The one thing to tell the player right now, most urgent first. Hex's own
 * listener status ("Listening") never shows as is: it reads as "recording".
 */
export function describe(state: State, models: HexModel[]): Status {
  const { hex, session, install, phase, config } = state;
  if (install.state === "running") {
    return {
      tone: "busy", title: install.stage || "Installing Hex", step: 1,
      progress: install.total ? percent(install.received, install.total) : null,
      detail: install.total ? `${megabytes(install.received)} of ${megabytes(install.total)}` : undefined,
    };
  }
  if (!hex.installed) {
    return {
      tone: "setup", title: "Set up dictation", step: 1, action: "install",
      detail: install.state === "failed" ? `Install failed: ${install.error}` : undefined,
    };
  }
  if (phase === "recording" || hex.capture === "recording") {
    return { tone: "recording", title: "Recording…", instruction: "recording" };
  }
  if (phase === "transcribing" || hex.capture === "transcribing") return { tone: "busy", title: "Transcribing…" };
  if (session.kind === "desktop" && !hex.running) {
    return { tone: "off", title: "Hex isn't running", detail: "In Desktop Mode HexDeck uses the Hex you start yourself." };
  }
  if (session.kind !== "desktop") {
    if (!config.enabled) return { tone: "off", title: "Off", detail: "Hex is stopped and its memory is free." };
    if (!hex.running) {
      return hex.service_error
        ? { tone: "warn", title: "Hex isn't running", detail: hex.service_error, action: "restart" }
        : { tone: "busy", title: "Starting Hex…" };
    }
  }
  const preparing = hex.model.preparing;
  if (preparing) {
    const model = models.find((candidate) => isPreparing(candidate, preparing));
    const total = model ? parseSize(model.size) : null;
    const received = hex.model.downloaded_bytes ?? 0;
    return {
      tone: "busy", title: `Downloading ${model?.name ?? preparing}`,
      progress: total ? percent(received, total) : null,
      detail: total ? `${megabytes(received)} of ${model?.size} · ${percent(received, total).toFixed(0)}%` : megabytes(received),
    };
  }
  if (hex.model.error) return { tone: "warn", title: "Model problem", detail: hex.model.error, action: "models" };
  if (needsModel(state)) return { tone: "setup", title: "Set up dictation", step: 2, action: "models" };
  if (session.kind === "gamescope" && hex.external) {
    return {
      tone: "ok", title: "Ready", instruction: "ready", action: "takeover",
      detail: "Using a Hex that was already running. If text doesn't reach your game, run Hex for Game Mode.",
    };
  }
  return {
    tone: "ok", title: "Ready", instruction: "ready",
    detail: session.kind === "desktop" ? "Desktop Mode · using your Hex" : undefined,
  };
}

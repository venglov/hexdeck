import { Field, Navigation, ProgressBar } from "@decky/ui";
import { toaster } from "@decky/api";
import { Fragment } from "react";

export const toast = (body: string, title = "HexDeck") => toaster.toast({ title, body, duration: 3500 });

export const truncate = (text: string, length = 140) => (text.length > length ? `${text.slice(0, length - 1)}…` : text);

/** The full-screen settings page, and the tab it opens on. */
export const PAGE_ROUTE = "/hexdeck";
export type PageTab = "models" | "controls" | "text" | "audio" | "help";
let requestedTab: PageTab = "models";
export const takeRequestedTab = () => requestedTab;
export const openPage = (tab: PageTab = "models") => {
  requestedTab = tab;
  Navigation.Navigate(PAGE_ROUTE);
  Navigation.CloseSideMenus();
};

/** Steam's blue, and the greys its secondary text uses. */
export const COLORS = { accent: "#1a9fff", muted: "#8b929a", ok: "#59bf40", recording: "#ff5c5c", warn: "#ffc82c" } as const;

/** Classes shared by the panel and the page; Steam adds `gpfocus` to the focused element. */
export const STYLES = `
.hexdeck-key { display: inline-block; padding: 0 6px; margin: 0 1px; border: 1px solid rgba(255,255,255,.35); border-radius: 4px; font-size: 0.85em; font-weight: 600; line-height: 1.5; white-space: nowrap; }
.hexdeck-item { border-radius: 4px; outline: none; cursor: pointer; }
.hexdeck-item.gpfocus, .hexdeck-item:hover, .hexdeck-item:focus { background: rgba(255,255,255,.14); box-shadow: 0 0 0 2px rgba(255,255,255,.85); }
.hexdeck-card { background: rgba(255,255,255,.05); border-radius: 4px; }
.hexdeck-chip { display: inline-block; padding: 1px 8px; border-radius: 3px; font-size: 12px; background: rgba(26,159,255,.18); color: #66c0ff; white-space: nowrap; }
@keyframes hexdeck-pulse { 50% { opacity: .35; } }
`;

/** Controller buttons as keycaps: [L4] + [R4]. */
export function Keys({ buttons }: { buttons: string[] }) {
  if (!buttons.length) return <span>no binding</span>;
  return (
    <span style={{ whiteSpace: "nowrap" }}>
      {buttons.map((button, index) => (
        <Fragment key={button}>
          {index > 0 && " + "}
          <span className="hexdeck-key">{button}</span>
        </Fragment>
      ))}
    </span>
  );
}

/**
 * A progress bar the width of its container. Steam's ProgressBarWithInfo puts
 * its bar and status line beside the label, and in the Quick Access panel's
 * narrow width that row runs past the right edge. Here the text is the
 * Field's label and description and the bare bar sits below them.
 */
export function ProgressRow({ label, progress, detail }: { label: string; progress?: number; detail?: string }) {
  return (
    <Field label={label} description={detail} childrenLayout="below" childrenContainerWidth="max" bottomSeparator="none">
      <Bar progress={progress} />
    </Field>
  );
}

export function Bar({ progress }: { progress?: number }) {
  return (
    <div style={{ width: "100%", padding: "6px 0 2px", boxSizing: "border-box" }}>
      <ProgressBar nProgress={progress} indeterminate={progress === undefined} />
    </div>
  );
}

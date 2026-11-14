import { ConfirmModal, DialogButton, DropdownItem, Field, Focusable, ModalRoot, showModal } from "@decky/ui";
import { ReactNode, useState } from "react";
import { BsCheckLg, BsDownload, BsInfoCircle } from "react-icons/bs";

import {
  HexModel,
  ROLE_LABELS,
  Role,
  bytesLabel,
  cancelModelDownload,
  languageName,
  megabytes,
  parseSize,
  percent,
  removeModel,
  supportedLanguages,
} from "../api";
import { Bar, COLORS, toast } from "../common";
import { Loaded, isPreparing, languageFor, understands } from "../state";

const isFound = (model: HexModel) => (model.source ?? "").startsWith("found");

/** How the model treats the languages it knows. */
function languageNote(model: HexModel): string {
  switch (model.language_mode) {
    case "automatic": return "Hears which of these you speak, with no language setting";
    case "choice": return model.detects_language
      ? "Detects which of these you speak, or takes the one you pick"
      : "Takes the one of these you pick";
    default: return "";
  }
}

const languageCount = (model: HexModel) => {
  const languages = supportedLanguages(model);
  return languages.length === 1 ? languageName(languages[0]) : `${languages.length} languages`;
};

/** Everything about one model, with the actions the list has on buttons. */
function ModelDetails({ model, speak, primary, onDelete, closeModal }: {
  model: HexModel; speak: string;
  primary?: { label: string; run: () => void };
  onDelete?: () => void;
  closeModal?: () => void;
}) {
  const languages = supportedLanguages(model);
  const note = languageNote(model);
  const then = (run: () => void) => () => { closeModal?.(); run(); };
  return (
    <ModalRoot closeModal={closeModal} onCancel={closeModal}>
      <div style={{ fontSize: "20px", fontWeight: 600, marginBottom: "6px" }}>{model.name}</div>
      {model.description && <div style={{ marginBottom: "6px" }}>{model.description}</div>}
      <div style={{ color: COLORS.muted, fontSize: "13px", marginBottom: "14px" }}>
        {[model.wait && `${model.wait} after 30 s of talking`, model.size,
          model.selected ? "in use" : model.installed ? "downloaded" : "not downloaded"].filter(Boolean).join(" · ")}
      </div>
      <div style={{ fontWeight: 600, marginBottom: "4px" }}>Languages ({languages.length})</div>
      {note && <div style={{ color: COLORS.muted, fontSize: "13px", marginBottom: "6px" }}>{note}.</div>}
      <div style={{ fontSize: "13px", lineHeight: 1.6, marginBottom: "14px" }}>
        {languages.length === 0 && "Hex doesn't say"}
        {languages.map((code, index) => (
          <span key={code} style={code === speak ? { color: COLORS.accent, fontWeight: 600 } : undefined}>
            {languageName(code)}{index < languages.length - 1 ? ", " : ""}
          </span>
        ))}
      </div>
      {model.vocabulary && (
        <div style={{ color: COLORS.muted, fontSize: "13px", marginBottom: "14px" }}>
          {model.vocabulary === "none" ? "Doesn't read your vocabulary." : "Reads your vocabulary (Text tab)."}
        </div>
      )}
      {isFound(model) && (
        <div style={{ color: COLORS.muted, fontSize: "13px", marginBottom: "14px" }}>
          Another app downloaded this file, so HexDeck leaves it alone.
        </div>
      )}
      <Focusable flow-children="horizontal" style={{ display: "flex", gap: "10px" }}>
        {primary && <DialogButton onClick={then(primary.run)}>{primary.label}</DialogButton>}
        {onDelete && <DialogButton onClick={then(onDelete)}>Delete ({model.size})</DialogButton>}
        <DialogButton onClick={closeModal}>Close</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

/**
 * The model picker. It starts from the language you speak: Hex's picks for
 * it as cards, then the other models that understand it, then what you have
 * downloaded for other languages; the rest stay folded away. One row is one
 * model: A uses or downloads it, X deletes it, Y opens its details.
 */
export function ModelsTab({ data }: { data: Loaded }) {
  const { state, models, guide, diskFree, speak, preparing, choose, setSpeak, reloadModels } = data;
  const [showOthers, setShowOthers] = useState(false);

  if (!state.hex.running) {
    return <Field label="Models" description={state.hex.installed
      ? "Available once Hex is running. Turn Dictation on in the HexDeck panel."
      : "Install Hex from the HexDeck panel first."} />;
  }

  const picks = (guide[speak] ?? []).filter(([id]) => models.some((model) => model.id === id));
  const roles = new Map<string, Role>(picks);
  const byId = (id: string) => models.find((model) => model.id === id)!;
  const order = (a: HexModel, b: HexModel) =>
    Number(b.selected) - Number(a.selected) || Number(b.installed) - Number(a.installed)
    || (a.wait_seconds ?? 99) - (b.wait_seconds ?? 99);
  const rest = models.filter((model) => !roles.has(model.id));
  const also = rest.filter((model) => understands(model, speak)).sort(order);
  const kept = rest.filter((model) => !understands(model, speak) && (model.installed || model.selected || isPreparing(model, preparing))).sort(order);
  const others = rest.filter((model) => !also.includes(model) && !kept.includes(model));

  const installed = models.filter((model) => model.installed);
  const used = installed.reduce((sum, model) => sum + (parseSize(model.size) ?? 0), 0);
  const summary = [
    `${installed.length} downloaded${used ? ` (${bytesLabel(used)})` : ""}`,
    diskFree != null && `${bytesLabel(diskFree)} free`,
  ].filter(Boolean).join(" · ");

  const speakName = speak === "auto" ? "any language" : languageName(speak);

  const remove = (model: HexModel) => showModal(
    <ConfirmModal
      strTitle={`Delete ${model.name}?`}
      strDescription={`Frees ${model.size}. You can download it again whenever you like.`}
      strOKButtonText="Delete"
      bDestructiveWarning
      onOK={async () => {
        const answer = await removeModel(model.id);
        toast(answer.ok ? `${model.name} deleted, ${model.size} freed` : answer.error ?? "Couldn't delete the model");
        reloadModels();
      }}
    />,
  );

  const deletable = (model: HexModel) => model.installed && !model.selected && !isFound(model) && !preparing;

  /** What A does on a model, and what its right-hand side shows. */
  const primary = (model: HexModel): { label: string; run: () => void } | undefined => {
    if (isPreparing(model, preparing)) {
      return { label: "Cancel download", run: async () => { await cancelModelDownload(); reloadModels(); } };
    }
    if (model.selected) return undefined;
    if (preparing) return { label: "Wait for the download", run: () => toast("One download at a time. Cancel the one running to start another.") };
    return model.installed
      ? { label: `Use ${model.name}`, run: () => choose(model) }
      : { label: `Download ${model.size}`, run: () => choose(model) };
  };

  const details = (model: HexModel) => showModal(
    <ModelDetails model={model} speak={speak} primary={primary(model)} onDelete={deletable(model) ? () => remove(model) : undefined} />,
  );

  const actions = (model: HexModel) => {
    const action = primary(model);
    const language = languageFor(model, speak);
    return {
      onActivate: action ? action.run : () => details(model),
      onClick: action ? action.run : () => details(model),
      onOKActionDescription: action ? action.label + (language && language !== "auto" && !isPreparing(model, preparing) ? ` in ${languageName(language)}` : "") : "Details",
      onSecondaryButton: deletable(model) ? () => remove(model) : undefined,
      onSecondaryActionDescription: deletable(model) ? "Delete" : undefined,
      onOptionsButton: () => details(model),
      onOptionsActionDescription: "Details",
    };
  };

  /** In use / Use / Download / progress: the state at the row's right edge. */
  const stateLabel = (model: HexModel): ReactNode => {
    if (isPreparing(model, preparing)) {
      const total = parseSize(model.size);
      const received = state.hex.model.downloaded_bytes ?? 0;
      return (
        <div>
          <div style={{ fontSize: "12px", color: COLORS.accent }}>
            {total ? `${megabytes(received)} of ${model.size} · ${percent(received, total).toFixed(0)}%` : megabytes(received)} · A cancels
          </div>
          <Bar progress={total ? percent(received, total) : undefined} />
        </div>
      );
    }
    if (model.selected) return <span style={{ color: COLORS.ok, fontWeight: 600 }}><BsCheckLg /> In use</span>;
    if (model.installed) return <span style={{ fontWeight: 600 }}>Use</span>;
    return <span style={{ color: COLORS.accent, fontWeight: 600 }}><BsDownload /> {model.size}</span>;
  };

  const info = (model: HexModel) => (
    <span
      role="button" aria-label={`Details of ${model.name}`}
      style={{ padding: "4px", color: COLORS.muted, display: "inline-flex" }}
      onClick={(event) => { event.stopPropagation(); details(model); }}
    >
      <BsInfoCircle />
    </span>
  );

  const card = ([id, role]: [string, Role], index: number) => {
    const model = byId(id);
    return (
      <Focusable
        key={id}
        className="hexdeck-item hexdeck-card"
        style={{
          padding: "12px 14px", display: "flex", flexDirection: "column", gap: "6px", minWidth: 0,
          border: `2px solid ${index === 0 ? COLORS.accent : "transparent"}`,
        }}
        {...actions(model)}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="hexdeck-chip">{ROLE_LABELS[role]}</span>
          {info(model)}
        </div>
        <div style={{ fontWeight: 600, fontSize: "15px" }}>{model.name}</div>
        <div style={{ color: COLORS.muted, fontSize: "12px", flex: 1 }}>{model.description}</div>
        <div style={{ color: COLORS.muted, fontSize: "12px" }}>
          {[model.wait, languageCount(model), model.installed ? model.size : null].filter(Boolean).join(" · ")}
        </div>
        <div style={{ fontSize: "13px" }}>{stateLabel(model)}</div>
      </Focusable>
    );
  };

  const row = (model: HexModel) => (
    <Focusable
      key={model.id}
      className="hexdeck-item"
      style={{
        display: "grid", gridTemplateColumns: "minmax(0, 1fr) 96px 104px 150px 24px", gap: "10px",
        alignItems: "center", padding: "8px 10px", fontSize: "13px", borderTop: "1px solid rgba(255,255,255,.08)",
      }}
      {...actions(model)}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: "14px" }}>{model.name}</div>
        <div style={{ color: COLORS.muted, fontSize: "12px" }}>{model.description || (isFound(model) ? "Found on this Deck, not tested by Hex" : "")}</div>
      </div>
      <span style={{ color: COLORS.muted }}>{model.wait ?? ""}</span>
      <span style={{ color: COLORS.muted }}>{languageCount(model)}</span>
      <div style={{ textAlign: "right" }}>{stateLabel(model)}</div>
      {info(model)}
    </Focusable>
  );

  const heading = (text: string) => (
    <div style={{ color: COLORS.muted, fontSize: "12px", textTransform: "uppercase", letterSpacing: ".05em", margin: "18px 0 6px" }}>{text}</div>
  );

  return (
    <>
      <DropdownItem
        label="I speak"
        description={summary}
        menuLabel="The language you dictate in"
        rgOptions={Object.keys(guide).map((code) => ({
          data: code,
          label: code === "auto" ? "Any language (detect it)" : languageName(code),
        }))}
        selectedOption={speak}
        onChange={(option) => setSpeak(option.data)}
      />
      {state.hex.model.error && <Field label="Model problem" description={state.hex.model.error} />}

      {picks.length > 0 && (
        <>
          {heading(speak === "auto" ? "Hex's picks when it should detect the language" : `Hex's picks for ${speakName}`)}
          <Focusable
            flow-children="horizontal"
            style={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(picks.length, 2)}, minmax(0, 1fr))`, gap: "12px" }}
          >
            {picks.map(card)}
          </Focusable>
        </>
      )}

      {also.length > 0 && (
        <>
          {heading(speak === "auto" ? `Other models that detect the language (${also.length})` : `Also understand ${speakName} (${also.length})`)}
          {also.map(row)}
        </>
      )}

      {kept.length > 0 && (
        <>
          {heading(`Downloaded, for other languages (${kept.length})`)}
          {kept.map(row)}
        </>
      )}

      {others.length > 0 && (
        <div style={{ marginTop: "18px" }}>
          <DialogButton onClick={() => setShowOthers(!showOthers)}>
            {showOthers ? "Hide models for other languages" : `Show ${others.length} models for other languages`}
          </DialogButton>
          {showOthers && <div style={{ marginTop: "8px" }}>{others.map(row)}</div>}
        </div>
      )}
    </>
  );
}

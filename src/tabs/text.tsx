import { ButtonItem, DialogButton, DropdownItem, Field, Focusable, TextField, ToggleField } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";

import { addVocabulary, getVocabulary, pasteLast, removeVocabulary } from "../api";
import { toast, truncate } from "../common";
import { Loaded } from "../state";

/** Names and terms Hex should recognize: character names, places, game jargon. */
function Vocabulary({ data }: { data: Loaded }) {
  const [terms, setTerms] = useState<string[] | null>(null);
  const [draft, setDraft] = useState("");
  const [problem, setProblem] = useState("");

  const load = useCallback(async () => {
    const answer = await getVocabulary();
    if (answer.ok) setTerms(answer.terms);
    else setProblem(answer.error ?? "Hex didn't list its vocabulary");
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    const term = draft.trim();
    if (!term) return setProblem("Type a word or a name first");
    const answer = await addVocabulary(term);
    if (!answer.ok) return setProblem(answer.error ?? "Hex didn't take that term");
    setDraft("");
    setProblem("");
    load();
  };

  const remove = async (term: string) => {
    const answer = await removeVocabulary(term);
    if (!answer.ok) toast(answer.error ?? `Couldn't remove ${term}`);
    load();
  };

  const reads = data.selected?.vocabulary;
  const note = !data.selected || !reads ? "Names and terms for Hex to recognize. Not every model reads them."
    : reads === "none" ? `${data.selected.name} doesn't read the vocabulary; a model marked "Reads your vocabulary" does.`
      : `${data.selected.name} reads these names and terms.`;

  return (
    <>
      <Field label="Vocabulary" description={problem || note} childrenLayout="below" childrenContainerWidth="max">
        <Focusable flow-children="horizontal" style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <TextField
              value={draft}
              placeholder="Novigrad"
              onChange={(event) => { setDraft(event.target.value); setProblem(""); }}
            />
          </div>
          <DialogButton style={{ width: "auto", minWidth: "90px", flex: "none" }} onClick={add}>Add</DialogButton>
        </Focusable>
      </Field>
      {(terms ?? []).map((term) => (
        <ButtonItem key={term} label={term} onClick={() => remove(term)}>Remove</ButtonItem>
      ))}
    </>
  );
}

/** Where the text goes once it's heard. */
export function TextTab({ data }: { data: Loaded }) {
  const { state, update } = data;
  const { config } = state;

  const again = async () => {
    const answer = await pasteLast();
    if (!answer.ok) toast(answer.error ?? "Couldn't insert the text again");
  };

  return (
    <>
      <DropdownItem
        label="Insert text by"
        description={config.output === "paste"
          ? "Hex pastes the text, in any language"
          : "Types on a virtual US keyboard, for games that ignore paste. Accents are dropped."}
        rgOptions={[
          { data: "paste", label: "Pasting (Hex)" },
          { data: "type", label: "Typing (US keyboard)" },
        ]}
        selectedOption={config.output}
        onChange={(option) => update("output", option.data)}
      />
      <ToggleField
        label="Press Enter after"
        description="Sends a chat message straight away. A line break in what you said never presses Enter."
        checked={config.press_enter}
        onChange={(value) => update("press_enter", value)}
      />
      {state.hex.running && (
        <ButtonItem
          label="Last dictation"
          description={state.last_text ? `“${truncate(state.last_text, 200)}”` : "Inserts the last text again if it missed the field"}
          disabled={config.output === "type" && !state.last_text}
          onClick={again}
        >
          {config.output === "type" ? "Type again" : "Paste again"}
        </ButtonItem>
      )}
      {state.hex.running && <Vocabulary data={data} />}
    </>
  );
}

"""What a Hex model does with its language setting.

``hex model list --json`` gives each model's languages but not whether the
model detects the language itself, or whether the language it is set to
reaches transcription at all. Hex's own Settings know both
(``ModelDefinition::supports_language_detection`` and
``accepts_language_hint`` in Hex's ``src/transcription/models.rs``); this
module mirrors them so the panel can say what the setting really does:

* ``automatic``: the model hears the language itself and has no language
  input (Parakeet v3, Granite). Whatever language Hex has saved for it,
  it understands every language it knows.
* ``choice``: the language goes to the model. Models that detect the
  language also take ``auto`` (Hex's "Auto"), which Hex offers first.
* ``fixed``: one language, no choice.

A model this table doesn't know (an import, a newer Hex) falls back to its
listed languages, as HexDeck 0.1 did.
"""

from __future__ import annotations

from typing import Optional

AUTO = "auto"

# Hex's LANGUAGES (src/transcription/languages.rs), in its order, without
# Auto. A model that lists "*" (Whisper) takes any of them.
HEX_LANGUAGES = (
    "en zh yue ja ko es fr de pt it ar hi bn vi ru uk nl pl tr sv da no fi cs el ro hu id ms th "
    "fa he bg hr et lv lt mt sk sl mk fil nn ca ta ur la mi ml cy te sr az kn br eu is hy ne mn "
    "bs kk sq sw gl mr pa si km sn yo so af oc ka be tg sd gu am yi lo uz fo ht ps tk sa lb my "
    "bo tl mg as tt haw ln ha ba"
).split()

# id -> (detects the language, takes a language). From Hex's catalog.
MODEL_TRAITS = {
    "parakeet_unified_en": (False, True),
    "parakeet_v2": (False, True),
    "parakeet_v3": (True, False),
    "orukeet": (True, False),
    "parakeet_ultra": (True, False),
    "granite_speech_5": (True, False),
    "whisper_large_v3_turbo": (True, True),
    "qwen3_asr06_b": (True, True),
    "sense_voice_small": (True, True),
    "nemotron_3_5_asr": (True, True),
    "qwencleo_asr_1_7b": (False, True),
    "ivrit_whisper_large_v3_turbo": (False, True),
    "cohere_transcribe": (False, True),
    "nb_whisper_medium": (False, True),
    "underdog_bark_3_pro": (False, False),
    "underdog_bark_3_clean": (False, False),
    "gigaam_v3": (False, False),
}


def model_languages(model: dict) -> list:
    """The model's own languages, with Whisper's "*" spelled out."""
    languages = [code for code in model.get("languages") or [] if isinstance(code, str)]
    if "*" in languages:
        listed = [code for code in languages if code != "*"]
        return list(HEX_LANGUAGES) + [code for code in listed if code not in HEX_LANGUAGES]
    return [code for code in languages if code != AUTO]


def language_info(model: dict) -> dict:
    """``language_mode``, ``detects_language`` (``None`` when unknown), and
    ``language_choices`` (Auto first where the model takes it)."""
    languages = model_languages(model)
    traits: Optional[tuple] = MODEL_TRAITS.get(str(model.get("id", "")))
    if traits is None:
        detects = AUTO in (model.get("languages") or []) or None
        choices = ([AUTO] if detects else []) + languages
        mode = "choice" if len(choices) > 1 else "fixed"
        return {"language_mode": mode, "detects_language": detects, "language_choices": choices}
    detects, takes_language = traits
    if detects and not takes_language:
        return {"language_mode": "automatic", "detects_language": True, "language_choices": [AUTO]}
    choices = ([AUTO] if detects else []) + (languages if takes_language else languages[:1])
    mode = "choice" if takes_language and len(choices) > 1 else "fixed"
    return {"language_mode": mode, "detects_language": detects, "language_choices": choices}

"""What Hex's speech-model picker says about each model, for the panel.

``hex model list --json`` names each model with its languages, size and
whether it streams, but not the line Hex's picker shows on its card, how
long it makes you wait, or which models Hex recommends for a language.
This module mirrors them from Hex's source so a model can be judged before
it is downloaded:

* ``BLURBS``: the picker's one line per model (``facts::blurb`` in
  ``src/rune_ui/picker/facts.rs``);
* ``REALTIME``: each model's speed, times real time
  (``ModelDefinition::realtime`` in ``src/transcription/models.rs``), which
  the picker turns into the wait after 30 seconds of talking;
* ``recommendations``: Hex's picks per language with their badges
  (``choices_for_runtime`` in ``models.rs``).

Update the tables when Hex adds or retunes a model. A model they don't
know (an import, a newer Hex) shows only what ``hex model list`` says.
"""

from __future__ import annotations

from typing import Optional

from .languages import AUTO, LISTED_CODES

BLURBS = {
    "parakeet_unified_en": "Writes while you talk, so the text is ready when you let go",
    "cohere_transcribe": "The fewest wrong words, in 14 languages. A big download",
    "whisper_large_v3_turbo": "Almost any language, and it reads your vocabulary",
    "parakeet_v2": "The English model before Parakeet Unified",
    "parakeet_v3": "25 European languages, and it hears which one you speak",
    "orukeet": "A Parakeet v3 fine-tune, a bit more accurate in 20 of its 25 languages",
    "parakeet_ultra": "Parakeet v3, retrained for fewer wrong words",
    "qwen3_asr06_b": "Chinese and 29 more, and it reads your vocabulary",
    "qwencleo_asr_1_7b": "Egyptian Arabic, mixed with English",
    "ivrit_whisper_large_v3_turbo": "Whisper, tuned for Hebrew",
    "sense_voice_small": "Chinese, Japanese, Korean and English. A small download",
    "underdog_bark_3_pro": "Parakeet, tuned for fewer wrong words in English",
    "underdog_bark_3_clean": "English, with the ums and uhs taken out",
    "nemotron_3_5_asr": "Writes while you talk, in 27 languages",
    "gigaam_v3": "Russian, with punctuation. A small download",
    "nb_whisper_medium": "Whisper, tuned for Norwegian by its National Library",
    "granite_speech_5": "IBM's model for seven languages, with punctuation",
}

# Times real time ("~33x" in Hex).
REALTIME = {
    "parakeet_unified_en": 163,
    "parakeet_v2": 55,
    "parakeet_v3": 33,
    "orukeet": 33,
    "whisper_large_v3_turbo": 19,
    "qwen3_asr06_b": 16,
    "qwencleo_asr_1_7b": 9,
    "ivrit_whisper_large_v3_turbo": 19,
    "sense_voice_small": 72,
    "cohere_transcribe": 73,
    "underdog_bark_3_pro": 33,
    "underdog_bark_3_clean": 33,
    "parakeet_ultra": 33,
    "nemotron_3_5_asr": 25,
    "gigaam_v3": 40,
    "nb_whisper_medium": 17,
    "granite_speech_5": 25,
}

# Models that write while you talk (``ModelDefinition::streams``), for a
# list reply that doesn't say.
STREAMING = {"parakeet_unified_en", "nemotron_3_5_asr"}

TALK_SECONDS = 30.0

# Badges, as Hex's picker words them.
RECOMMENDED = "recommended"
FASTEST = "fastest"
MOST_ACCURATE = "most_accurate"
VOCABULARY = "vocabulary"
ROLE_LABELS = {
    RECOMMENDED: "Recommended",
    FASTEST: "Fastest",
    MOST_ACCURATE: "Fewest wrong words",
    VOCABULARY: "Reads your vocabulary",
}

# Hex's PARAKEET_V3_LANGUAGES and QWEN_LANGUAGES (artifacts.rs), for the
# routing's fallbacks.
PARAKEET_V3_LANGUAGES = (
    "bg hr cs da nl en et fi fr de el hu it lv lt mt pl pt ro ru sk sl es sv uk"
).split()
QWEN_LANGUAGES = (
    "zh en yue ar de fr es pt id it ko ru th vi ja tr hi ms nl sv da fi pl cs fil fa el ro hu mk"
).split()

_ROUTING = {
    AUTO: (("whisper_large_v3_turbo", RECOMMENDED), ("qwen3_asr06_b", FASTEST)),
    "en": (("parakeet_unified_en", RECOMMENDED), ("cohere_transcribe", MOST_ACCURATE),
           ("whisper_large_v3_turbo", VOCABULARY)),
    "zh": (("qwen3_asr06_b", RECOMMENDED), ("sense_voice_small", FASTEST),
           ("whisper_large_v3_turbo", VOCABULARY)),
    "yue": (("qwen3_asr06_b", RECOMMENDED), ("whisper_large_v3_turbo", VOCABULARY)),
    "ko": (("qwen3_asr06_b", RECOMMENDED), ("whisper_large_v3_turbo", VOCABULARY)),
    "ja": (("whisper_large_v3_turbo", RECOMMENDED), ("sense_voice_small", FASTEST)),
    "el": (("cohere_transcribe", RECOMMENDED), ("whisper_large_v3_turbo", VOCABULARY)),
    "mt": (("parakeet_v3", RECOMMENDED),),
    "ar": (("whisper_large_v3_turbo", RECOMMENDED), ("cohere_transcribe", MOST_ACCURATE)),
    "he": (("ivrit_whisper_large_v3_turbo", RECOMMENDED), ("whisper_large_v3_turbo", VOCABULARY)),
    "ru": (("gigaam_v3", RECOMMENDED), ("whisper_large_v3_turbo", VOCABULARY)),
    "no": (("nb_whisper_medium", RECOMMENDED), ("whisper_large_v3_turbo", VOCABULARY)),
    "vi": (("qwen3_asr06_b", RECOMMENDED), ("cohere_transcribe", MOST_ACCURATE),
           ("whisper_large_v3_turbo", VOCABULARY)),
}
for _code in ("fi", "sv", "da"):
    _ROUTING[_code] = (("whisper_large_v3_turbo", RECOMMENDED), ("parakeet_v3", FASTEST))
for _code in ("tr", "ms", "fil", "fa", "mk"):
    _ROUTING[_code] = (("whisper_large_v3_turbo", RECOMMENDED),)


def recommendations(language: str) -> list:
    """Hex's picks for ``language`` as ``[model id, badge]`` pairs, best
    first (``choices_for_runtime``)."""
    picks = _ROUTING.get(language)
    if picks is None:
        if language in PARAKEET_V3_LANGUAGES:
            picks = (("parakeet_v3", RECOMMENDED), ("whisper_large_v3_turbo", VOCABULARY))
        elif language in QWEN_LANGUAGES:
            picks = (("qwen3_asr06_b", RECOMMENDED), ("whisper_large_v3_turbo", VOCABULARY))
        else:
            picks = (("whisper_large_v3_turbo", RECOMMENDED),)
    return [list(pick) for pick in picks]


def all_recommendations() -> dict:
    """Hex's picks for Auto and every language its Settings list."""
    return {code: recommendations(code) for code in (AUTO,) + LISTED_CODES}


def wait_seconds(model: dict) -> Optional[float]:
    """Seconds between letting go and the text after 30 seconds of talking:
    zero for a model that writes while you talk, ``None`` when unknown."""
    model_id = str(model.get("id", ""))
    if model.get("streams") or model_id in STREAMING:
        return 0.0
    factor = REALTIME.get(model_id)
    return TALK_SECONDS / factor if factor else None


def wait_label(seconds: Optional[float]) -> Optional[str]:
    """The wait as Hex's picker says it: "No wait", "Under 1 s wait", "2 s wait"."""
    if seconds is None:
        return None
    if seconds == 0:
        return "No wait"
    if seconds < 1:
        return "Under 1 s wait"
    # Rust's f32::round goes half away from zero; Python's round doesn't.
    return f"{max(1, int(seconds + 0.5))} s wait"


def model_facts(model: dict) -> dict:
    """``description`` (empty when Hex has none), ``wait`` and
    ``wait_seconds`` (``None`` when unknown)."""
    seconds = wait_seconds(model)
    return {
        "description": BLURBS.get(str(model.get("id", "")), ""),
        "wait": wait_label(seconds),
        "wait_seconds": seconds,
    }

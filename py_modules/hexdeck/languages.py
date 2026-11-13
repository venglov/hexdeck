"""What a Hex model does with its language setting, and which languages it knows.

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

# Hex's LANGUAGES (src/transcription/languages.rs): the languages Settings
# offers, in its order and with its names, without Auto. A model that lists
# "*" (Whisper) takes every one of them.
LISTED_LANGUAGES = (
    ("en", "English"), ("zh", "Mandarin Chinese"), ("yue", "Cantonese"), ("ja", "Japanese"),
    ("ko", "Korean"), ("es", "Spanish"), ("fr", "French"), ("de", "German"),
    ("pt", "Portuguese"), ("it", "Italian"), ("ar", "Arabic"), ("hi", "Hindi"),
    ("bn", "Bangla"), ("vi", "Vietnamese"), ("ru", "Russian"), ("uk", "Ukrainian"),
    ("nl", "Dutch"), ("pl", "Polish"), ("tr", "Turkish"), ("sv", "Swedish"),
    ("da", "Danish"), ("no", "Norwegian"), ("fi", "Finnish"), ("cs", "Czech"),
    ("el", "Greek"), ("ro", "Romanian"), ("hu", "Hungarian"), ("id", "Indonesian"),
    ("ms", "Malay"), ("th", "Thai"), ("fa", "Persian"), ("he", "Hebrew"),
    ("bg", "Bulgarian"), ("hr", "Croatian"), ("et", "Estonian"), ("lv", "Latvian"),
    ("lt", "Lithuanian"), ("mt", "Maltese"), ("sk", "Slovak"), ("sl", "Slovenian"),
    ("mk", "Macedonian"), ("fil", "Filipino"),
)

# Hex's OTHER_LANGUAGES: names for the rest of Whisper's languages, which
# Settings lists only for a model that declares them (an import).
OTHER_LANGUAGES = (
    ("nn", "Norwegian Nynorsk"), ("ca", "Catalan"), ("ta", "Tamil"), ("ur", "Urdu"),
    ("la", "Latin"), ("mi", "Maori"), ("ml", "Malayalam"), ("cy", "Welsh"),
    ("te", "Telugu"), ("sr", "Serbian"), ("az", "Azerbaijani"), ("kn", "Kannada"),
    ("br", "Breton"), ("eu", "Basque"), ("is", "Icelandic"), ("hy", "Armenian"),
    ("ne", "Nepali"), ("mn", "Mongolian"), ("bs", "Bosnian"), ("kk", "Kazakh"),
    ("sq", "Albanian"), ("sw", "Swahili"), ("gl", "Galician"), ("mr", "Marathi"),
    ("pa", "Punjabi"), ("si", "Sinhala"), ("km", "Khmer"), ("sn", "Shona"),
    ("yo", "Yoruba"), ("so", "Somali"), ("af", "Afrikaans"), ("oc", "Occitan"),
    ("ka", "Georgian"), ("be", "Belarusian"), ("tg", "Tajik"), ("sd", "Sindhi"),
    ("gu", "Gujarati"), ("am", "Amharic"), ("yi", "Yiddish"), ("lo", "Lao"),
    ("uz", "Uzbek"), ("fo", "Faroese"), ("ht", "Haitian Creole"), ("ps", "Pashto"),
    ("tk", "Turkmen"), ("sa", "Sanskrit"), ("lb", "Luxembourgish"), ("my", "Burmese"),
    ("bo", "Tibetan"), ("tl", "Tagalog"), ("mg", "Malagasy"), ("as", "Assamese"),
    ("tt", "Tatar"), ("haw", "Hawaiian"), ("ln", "Lingala"), ("ha", "Hausa"),
    ("ba", "Bashkir"), ("jw", "Javanese"), ("su", "Sundanese"),
)

LISTED_CODES = tuple(code for code, _ in LISTED_LANGUAGES)
LANGUAGE_NAMES = {code: name for code, name in LISTED_LANGUAGES + OTHER_LANGUAGES}

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


def language_name(code: str) -> str:
    """Hex's English name for ``code``, or the code when Hex has none."""
    return "Automatic" if code == AUTO else LANGUAGE_NAMES.get(code, code)


def model_languages(model: dict) -> list:
    """The languages Hex offers with the model, as its Settings order them
    (``ModelDefinition::language_choices``): the listed languages it knows
    ("*" is all of them), then any other language it declares."""
    declared = [code for code in model.get("languages") or [] if isinstance(code, str) and code != AUTO]
    anything = "*" in declared
    listed = [code for code in LISTED_CODES if anything or code in declared]
    others = [code for code in declared if code != "*" and code not in LISTED_CODES]
    return listed + list(dict.fromkeys(others))


def language_info(model: dict) -> dict:
    """``language_mode``, ``detects_language`` (``None`` when unknown),
    ``language_choices`` (Auto first where the model takes it), and
    ``supported_languages`` (what it understands, whatever the setting)."""
    languages = model_languages(model)
    traits: Optional[tuple] = MODEL_TRAITS.get(str(model.get("id", "")))
    if traits is None:
        detects = AUTO in (model.get("languages") or []) or None
        choices = ([AUTO] if detects else []) + languages
        mode = "choice" if len(choices) > 1 else "fixed"
        return {"language_mode": mode, "detects_language": detects, "language_choices": choices,
                "supported_languages": languages}
    detects, takes_language = traits
    if detects and not takes_language:
        return {"language_mode": "automatic", "detects_language": True, "language_choices": [AUTO],
                "supported_languages": languages}
    choices = ([AUTO] if detects else []) + (languages if takes_language else languages[:1])
    mode = "choice" if takes_language and len(choices) > 1 else "fixed"
    return {"language_mode": mode, "detects_language": detects, "language_choices": choices,
            "supported_languages": languages}

#!/usr/bin/env python3
"""Writes dev/preview-models.json, the model list preview.html's mock
backend returns: Hex's catalog run through HexDeck's own backend
(languages.py, catalog.py), so the preview shows what list_models sends.
Run it again after changing either table (``make preview`` does)."""

import json
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "py_modules"))

from hexdeck.catalog import PARAKEET_V3_LANGUAGES, QWEN_LANGUAGES, all_recommendations, model_facts  # noqa: E402
from hexdeck.languages import LANGUAGE_NAMES, language_info  # noqa: E402

COHERE = "en fr de es it pt nl pl el ar ja zh vi ko".split()
GRANITE = "en fr de es pt it ja".split()
NEMOTRON = "en es fr de it pt nl tr ru uk pl cs sk bg hr ro hu sv da fi et ar hi ja ko zh vi".split()

# id, name, languages, bytes, streams: Hex's models.rs and artifacts.rs.
CATALOG = [
    ("parakeet_unified_en", "Parakeet Unified English", ["en"], 731357568, True),
    ("parakeet_v2", "Parakeet v2", ["en"], 729574912, False),
    ("parakeet_v3", "Parakeet v3", PARAKEET_V3_LANGUAGES, 739508576, False),
    ("orukeet", "Orukeet", PARAKEET_V3_LANGUAGES, 739508704, False),
    ("whisper_large_v3_turbo", "Whisper large-v3-turbo", ["*"], 886381824, False),
    ("qwen3_asr06_b", "Qwen3-ASR 0.6B", QWEN_LANGUAGES, 850423456, False),
    ("qwencleo_asr_1_7b", "QwenCleo-ASR 1.7B", ["ar"], 2185030816, False),
    ("ivrit_whisper_large_v3_turbo", "ivrit.ai Whisper large-v3-turbo", ["he"], 886381536, False),
    ("sense_voice_small", "SenseVoice Small", ["zh", "yue", "en", "ja", "ko"], 252684608, False),
    ("cohere_transcribe", "Cohere Transcribe", COHERE, 2410655232, False),
    ("underdog_bark_3_pro", "Underdog Bark 3.0 Pro", ["en"], 739508480, False),
    ("underdog_bark_3_clean", "Underdog Bark 3.0 Clean", ["en"], 739508480, False),
    ("nemotron_3_5_asr", "Nemotron 3.5 ASR", NEMOTRON, 751094240, True),
    ("gigaam_v3", "GigaAM v3", ["ru"], 273724832, False),
    ("nb_whisper_medium", "NB-Whisper Medium", ["no"], 539212484, False),
    ("granite_speech_5", "Granite Speech 5.0", GRANITE, 505663136, False),
]


def size(count):
    return f"{count / 1e9:.1f} GB" if count >= 1e9 else f"{count // 1_000_000} MB"


models = []
for model_id, name, languages, count, streams in CATALOG:
    model = {"id": model_id, "name": name, "languages": list(languages), "size": size(count), "streams": streams}
    models.append({**model, **language_info(model), **model_facts(model)})

with open(os.path.join(here, "preview-models.json"), "w") as stream:
    json.dump({"models": models, "language_names": LANGUAGE_NAMES,
               "recommendations": all_recommendations()}, stream, indent=1)
    stream.write("\n")

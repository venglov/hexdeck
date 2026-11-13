"""HexDeck's own settings, saved as JSON in Decky's settings folder.

Hex's settings (model, language, keyboard shortcut, sounds) stay in Hex's
``settings.json`` and are changed through ``hex settings set``; this file
holds only what belongs to the plugin: the controller binding, how it
triggers, and how text reaches the game.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from .controller import normalize_binding

logger = logging.getLogger("hexdeck.config")

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    # Both back grips: games rarely map them, and Steam doesn't by default.
    "binding": ["L4", "R4"],
    # "hold": record while the binding is held. "toggle": press to start,
    # press again to finish.
    "trigger_mode": "hold",
    # "paste": Hex pastes, as on the desktop (any language).
    # "type": HexDeck types the transcript on a virtual US keyboard, for
    # games that ignore paste.
    "output": "paste",
    "press_enter": False,
    # Hold shorter than this and the recording is discarded (Hold mode).
    "min_hold_ms": 300,
    # "auto", or an X display such as ":1".
    "display": "auto",
    # Hide Hex's recording pill while HexDeck runs Hex in Game Mode; Decky
    # toasts show the state instead.
    "hide_hex_pill": True,
    "notifications": True,
    # A Hex executable to use instead of ~/.local/bin/hex.
    "hex_path": "",
    # Hex's indicator setting before HexDeck hid it, restored on exit.
    "saved_indicator_position": None,
}

CHOICES = {
    "trigger_mode": ("hold", "toggle"),
    "output": ("paste", "type"),
}


def validate(key: str, value: Any) -> Any:
    """The value to store for ``key``; raises ``ValueError`` when invalid."""
    if key not in DEFAULTS:
        raise ValueError(f"Unknown setting: {key}")
    if key in ("enabled", "press_enter", "hide_hex_pill", "notifications"):
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be true or false")
        return value
    if key in CHOICES:
        if value not in CHOICES[key]:
            raise ValueError(f"{key} must be one of {', '.join(CHOICES[key])}")
        return value
    if key == "binding":
        if not isinstance(value, list):
            raise ValueError("binding must be a list of buttons")
        return normalize_binding(value)
    if key == "min_hold_ms":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("min_hold_ms must be a number")
        return int(max(0, min(2000, value)))
    if key == "display":
        if not isinstance(value, str) or not (value == "auto" or (value.startswith(":") and value[1:].isdigit())):
            raise ValueError("display must be auto or an X display like :1")
        return value
    if key == "hex_path":
        if not isinstance(value, str):
            raise ValueError("hex_path must be a path")
        return value.strip()
    if key == "saved_indicator_position":
        if value is not None and not isinstance(value, str):
            raise ValueError("saved_indicator_position must be a string")
        return value
    raise ValueError(f"Unknown setting: {key}")  # pragma: no cover


class Config:
    def __init__(self, path: str):
        self.path = path
        self.values = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path) as stream:
                saved = json.load(stream)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            logger.warning("Ignoring unreadable settings %s: %s", self.path, error)
            return
        if not isinstance(saved, dict):
            return
        for key, value in saved.items():
            try:
                self.values[key] = validate(key, value)
            except ValueError as error:
                logger.warning("Ignoring saved %s: %s", key, error)

    def save(self) -> None:
        folder = os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=folder, delete=False, prefix=".settings-") as stream:
            json.dump(self.values, stream, indent=2, sort_keys=True)
            temporary = stream.name
        os.replace(temporary, self.path)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def set(self, key: str, value: Any) -> Any:
        self.values[key] = validate(key, value)
        self.save()
        return self.values[key]

    def public(self) -> dict:
        return {key: value for key, value in self.values.items() if key != "saved_indicator_position"}

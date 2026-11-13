"""Type text through a virtual uinput keyboard (US layout).

The "Type" output mode is for games that ignore paste. HexDeck asks Hex for
the transcript (``hex dictation stop --print``) and types it key by key here,
like Decktation's ydotool mode, but with no helper daemon: the plugin
backend is root and talks to ``/dev/uinput`` directly.

Only characters on a US keyboard can be typed. Common typographic
punctuation is folded to ASCII first; anything else is skipped and counted.
"""

from __future__ import annotations

import fcntl
import logging
import os
import struct
import threading
import time
import unicodedata
from typing import Optional

logger = logging.getLogger("hexdeck.typer")

EV_SYN, EV_KEY = 0x00, 0x01
SYN_REPORT = 0
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
BUS_VIRTUAL = 0x06

KEY_ENTER = 28
KEY_LEFTSHIFT = 42
KEY_BACKSPACE = 14

_LETTERS = dict(zip("qwertyuiop", range(16, 26)))
_LETTERS.update(zip("asdfghjkl", range(30, 39)))
_LETTERS.update(zip("zxcvbnm", range(44, 51)))

# character -> (keycode, shift)
KEYMAP: dict[str, tuple[int, bool]] = {}
for _char, _code in _LETTERS.items():
    KEYMAP[_char] = (_code, False)
    KEYMAP[_char.upper()] = (_code, True)
for _index, (_plain, _shifted) in enumerate(zip("1234567890", "!@#$%^&*()")):
    KEYMAP[_plain] = (2 + _index, False)
    KEYMAP[_shifted] = (2 + _index, True)
for _plain, _shifted, _code in (
    ("-", "_", 12), ("=", "+", 13), ("[", "{", 26), ("]", "}", 27),
    (";", ":", 39), ("'", '"', 40), ("`", "~", 41), ("\\", "|", 43),
    (",", "<", 51), (".", ">", 52), ("/", "?", 53),
):
    KEYMAP[_plain] = (_code, False)
    KEYMAP[_shifted] = (_code, True)
KEYMAP[" "] = (57, False)

# A newline in a transcript must never press Enter (that sends game chat);
# only the explicit "Press Enter after" setting does.
FOLD = {
    "\n": " ", "\r": " ", "\t": " ",
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    "…": "...", " ": " ", " ": " ",
}


def to_typeable(text: str) -> tuple[str, int]:
    """``text`` folded to US-keyboard characters, and how many were dropped."""
    out = []
    dropped = 0
    for char in text:
        char = FOLD.get(char, char)
        if all(c in KEYMAP for c in char):
            out.append(char)
            continue
        # é -> e, ñ -> n: strip accents rather than lose the letter.
        base = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
        if base and all(c in KEYMAP for c in base):
            out.append(base)
        else:
            dropped += 1
    return "".join(out), dropped


def key_sequence(text: str, press_enter: bool = False) -> list[tuple[int, int]]:
    """(keycode, value) events; value 1 is press, 0 release."""
    events: list[tuple[int, int]] = []
    for char in text:
        code, shift = KEYMAP[char]
        if shift:
            events.append((KEY_LEFTSHIFT, 1))
        events += [(code, 1), (code, 0)]
        if shift:
            events.append((KEY_LEFTSHIFT, 0))
    if press_enter:
        events += [(KEY_ENTER, 1), (KEY_ENTER, 0)]
    return events


def _event(kind: int, code: int, value: int) -> bytes:
    seconds = time.time()
    return struct.pack("llHHi", int(seconds), int((seconds % 1) * 1e6), kind, code, value)


class VirtualKeyboard:
    """A uinput keyboard, created on first use and kept for the session.

    Creating a device makes the compositor notice a hotplug; keeping one
    alive avoids losing the first keys of every message to that delay.
    """

    def __init__(self, key_delay: float = 0.006):
        self.fd: Optional[int] = None
        self.key_delay = key_delay
        self.lock = threading.Lock()

    def _open(self) -> int:
        if self.fd is not None:
            return self.fd
        fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
            for code in sorted({code for code, _ in KEYMAP.values()} | {KEY_LEFTSHIFT, KEY_BACKSPACE, KEY_ENTER}):
                fcntl.ioctl(fd, UI_SET_KEYBIT, code)
            # Legacy uinput_user_dev: name[80], id (4 x u16), ff_effects_max,
            # then absmax/absmin/absfuzz/absflat (4 x 64 x s32).
            name = b"HexDeck virtual keyboard"
            device = struct.pack("80sHHHHi", name, BUS_VIRTUAL, 0x1209, 0x4855, 1, 0) + bytes(4 * 64 * 4)
            os.write(fd, device)
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            raise
        self.fd = fd
        # Let the compositor pick the new device up before the first key.
        time.sleep(0.4)
        return fd

    def type(self, text: str, press_enter: bool = False) -> int:
        """Type ``text``; return how many characters couldn't be typed."""
        typeable, dropped = to_typeable(text)
        events = key_sequence(typeable, press_enter)
        with self.lock:
            fd = self._open()
            for code, value in events:
                os.write(fd, _event(EV_KEY, code, value) + _event(EV_SYN, SYN_REPORT, 0))
                time.sleep(self.key_delay)
        if dropped:
            logger.info("Skipped %d characters a US keyboard can't type", dropped)
        return dropped

    def close(self) -> None:
        with self.lock:
            if self.fd is not None:
                try:
                    fcntl.ioctl(self.fd, UI_DEV_DESTROY)
                except OSError:
                    pass
                os.close(self.fd)
                self.fd = None

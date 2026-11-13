"""Controller push-to-talk: watch the physical buttons, report the binding.

A reader thread decodes the controller's raw HID reports (``deck_hid``) and
feeds the set of held buttons to two small state machines, both pure logic so
they're tested without hardware:

* ``ComboDetector`` reports when the binding becomes held and released;
* ``BindingCapture`` records a new binding from what the player holds.

Reading hidraw doesn't take the device from Steam: games still see the
buttons. That's why the default binding uses the back grips, which games
rarely map.
"""

from __future__ import annotations

import logging
import os
import select
import threading
import time
from typing import Callable, Iterable, Optional

from .deck_hid import BUTTONS, button_states, disconnect_report, find_controllers

logger = logging.getLogger("hexdeck.controller")

MAX_BINDING_BUTTONS = 4
CAPTURE_TIMEOUT = 10.0


def normalize_binding(buttons: Iterable[str]) -> list[str]:
    """Known buttons in a stable order; raises on anything else."""
    chosen = list(dict.fromkeys(buttons))
    unknown = [name for name in chosen if name not in BUTTONS]
    if unknown:
        raise ValueError(f"Unknown button: {', '.join(unknown)}")
    if not 1 <= len(chosen) <= MAX_BINDING_BUTTONS:
        raise ValueError(f"A binding needs 1 to {MAX_BINDING_BUTTONS} buttons")
    return [name for name in BUTTONS if name in chosen]


class ComboDetector:
    """Edges of "every button in the binding is held"."""

    def __init__(self, binding: Iterable[str]):
        self.binding = frozenset(binding)
        self.active = False

    def set_binding(self, binding: Iterable[str]) -> None:
        self.binding = frozenset(binding)
        self.active = False

    def update(self, held: frozenset) -> Optional[str]:
        """``"press"``, ``"release"``, or ``None``."""
        now_active = bool(self.binding) and self.binding <= held
        if now_active == self.active:
            return None
        self.active = now_active
        return "press" if now_active else "release"

    def reset(self) -> Optional[str]:
        """Forget held state (controller lost); a held combo is released."""
        was = self.active
        self.active = False
        return "release" if was else None


class BindingCapture:
    """Record the chord the player holds, finishing when they let go.

    1. ``release``: wait for a quiet 250 ms, so the A press that started the
       capture in the menu doesn't become the binding;
    2. ``listening``/``holding``: grow the chord while buttons are added;
       once any button lifts, freeze it, so a staggered release can't
       shrink it;
    3. ``captured`` when everything is released, or ``cancelled``.
    """

    def __init__(self, deadline: float):
        self.deadline = deadline
        self.phase = "release"
        self.buttons: list[str] = []
        self.previous: frozenset = frozenset()
        self.releasing = False
        self.quiet_since: Optional[float] = None
        self.error = ""

    @property
    def active(self) -> bool:
        return self.phase in ("release", "listening", "holding")

    def cancel(self, reason: str = "Cancelled") -> None:
        if self.active:
            self.phase, self.error = "cancelled", reason

    def update(self, held: frozenset, now: float) -> None:
        if not self.active:
            return
        if now >= self.deadline:
            self.cancel("Timed out; the binding is unchanged")
            return
        if self.phase == "release":
            if held:
                self.quiet_since = None
            elif self.quiet_since is None:
                self.quiet_since = now
            elif now - self.quiet_since >= 0.25:
                self.phase = "listening"
            return
        if held:
            if self.previous - held:
                self.releasing = True
            if not self.releasing:
                if len(held) > MAX_BINDING_BUTTONS:
                    self.cancel(f"Use at most {MAX_BINDING_BUTTONS} buttons")
                    return
                self.buttons = [name for name in BUTTONS if name in held]
            self.phase = "holding"
        elif self.buttons:
            self.phase = "captured"
        self.previous = held

    def snapshot(self) -> dict:
        return {"phase": self.phase, "buttons": self.buttons, "error": self.error}


class ControllerReader:
    """Background thread reading the first Valve controller it finds."""

    def __init__(self, binding: Iterable[str], on_combo: Callable[[str], None],
                 on_capture: Callable[[dict], None] = lambda _snapshot: None):
        self.detector = ComboDetector(binding)
        self.on_combo = on_combo
        self.on_capture = on_capture
        self.capture: Optional[BindingCapture] = None
        self.held: frozenset = frozenset()
        self.device: Optional[str] = None
        self.error = ""
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread: Optional[threading.Thread] = None

    # -- Public ----------------------------------------------------------------

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stopping.clear()
        self.thread = threading.Thread(target=self._run, name="hexdeck-controller", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=2)

    def set_binding(self, binding: Iterable[str]) -> None:
        with self.lock:
            self.detector.set_binding(binding)

    def start_capture(self) -> dict:
        with self.lock:
            self.capture = BindingCapture(time.monotonic() + CAPTURE_TIMEOUT)
            # A combo held while capture starts must not stay "pressed".
            edge = self.detector.reset()
        if edge:
            self.on_combo(edge)
        return self.capture.snapshot()

    def cancel_capture(self) -> None:
        with self.lock:
            if self.capture:
                self.capture.cancel()

    def capture_snapshot(self) -> Optional[dict]:
        with self.lock:
            if self.capture is None:
                return None
            # Time out even when no reports arrive.
            self.capture.update(self.held, time.monotonic())
            return self.capture.snapshot()

    def snapshot(self) -> dict:
        return {"device": self.device, "error": self.error,
                "held": [name for name in BUTTONS if name in self.held]}

    # -- Thread ----------------------------------------------------------------

    def _handle(self, held: frozenset) -> None:
        edge = None
        finished = None
        with self.lock:
            self.held = held
            if self.capture is not None and self.capture.active:
                self.capture.update(held, time.monotonic())
                if not self.capture.active:
                    finished = self.capture.snapshot()
            else:
                edge = self.detector.update(held)
        if finished is not None:
            self.on_capture(finished)
        if edge:
            self.on_combo(edge)

    def _lost(self) -> None:
        with self.lock:
            self.held = frozenset()
            edge = self.detector.reset()
        if edge:
            self.on_combo(edge)

    def _run(self) -> None:
        while not self.stopping.is_set():
            node = next(find_controllers(), None)
            if node is None:
                self.device, self.error = None, "No Steam Deck controller found"
                self.stopping.wait(2.0)
                continue
            try:
                # hid-steam needs read/write access even to deliver input.
                fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)
            except OSError as error:
                self.device, self.error = None, f"Can't open {node}: {error.strerror}"
                self.stopping.wait(2.0)
                continue
            self.device, self.error = node, ""
            logger.info("Reading controller from %s", node)
            try:
                self._read_loop(fd)
            except OSError as error:
                logger.warning("Controller read failed: %s", error)
            finally:
                os.close(fd)
                self.device = None
                self._lost()

    def _read_loop(self, fd: int) -> None:
        while not self.stopping.is_set():
            readable, _, _ = select.select([fd], [], [], 0.2)
            if not readable:
                # Keep the capture's timeout moving.
                with self.lock:
                    capture = self.capture
                if capture is not None and capture.active:
                    self._handle(self.held)
                continue
            report = os.read(fd, 64)
            if not report:
                raise OSError("controller disconnected")
            if disconnect_report(report):
                self._handle(frozenset())
                continue
            states = button_states(report)
            if states is not None:
                held = frozenset(name for name, down in states.items() if down)
                if held != self.held:
                    self._handle(held)

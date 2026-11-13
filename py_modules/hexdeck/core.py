"""HexDeck's backend: the controller, Hex, and the Quick Access panel.

Threads:

* the controller reader (``controller.ControllerReader``) reports binding
  presses and releases;
* one dictation worker runs Hex commands in order, so a quick press and
  release can never reach Hex as stop-before-start;
* a session loop every few seconds finds the display, starts or restarts
  ``hex service`` in Game Mode, and refreshes Hex's status for the panel.

Decky RPC methods (``main.py``) call the public methods here from a thread
pool; ``emit`` sends events to the frontend for toasts.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any, Callable, Optional

from . import VERSION
from .config import Config
from .controller import ControllerReader
from .hexcli import EXIT_NO_SPEECH, EXIT_NOT_RUNNING, EXIT_OK, HexCli, HexResult, find_hex, model_file, setting_value
from .installer import Installer
from .languages import language_info
from .model_files import RemoveError, remove_model_files
from .service import HexService
from .session import Account, DisplayChoice, detect_display, find_account
from .typer import VirtualKeyboard

logger = logging.getLogger("hexdeck.core")

SESSION_INTERVAL = 3.0
STATUS_MAX_AGE = 1.5

# Keyboard shortcuts offered for Hex's own dictation hotkey (external or
# Bluetooth keyboards). Hex's names: option is Alt, control is Ctrl.
KEYBOARD_SHORTCUTS = [
    ("option+space", "Alt + Space"),
    ("control+space", "Ctrl + Space"),
    ("control+option+space", "Ctrl + Alt + Space"),
    ("f9", "F9"),
    ("f10", "F10"),
    ("f12", "F12"),
]


def transcript_text(reply: dict) -> str:
    """The text of a ``transcript`` reply."""
    text = reply.get("text")
    return text if isinstance(text, str) else ""


def last_history_text(reply: dict) -> str:
    """The newest entry's text from ``hex history --limit 1 --json``."""
    candidates: list = []
    for key in ("value", "entries", "history", "results", "dictations"):
        value = reply.get(key)
        if isinstance(value, list):
            candidates = value
            break
    for entry in candidates:
        if isinstance(entry, dict):
            for key in ("text", "final", "final_text", "transcript"):
                if isinstance(entry.get(key), str):
                    return entry[key]
    return ""


class HexDeck:
    def __init__(self, settings_dir: str, log_dir: str,
                 emit: Callable[[str, dict], None] = lambda _event, _payload: None,
                 account: Optional[Account] = None):
        self.config = Config(os.path.join(settings_dir, "settings.json"))
        self.account = account or find_account()
        self.emit_event = emit
        self.service = HexService(self.account, os.path.join(log_dir, "hex-service.log"))
        self.installer = Installer(self.account, on_change=self._on_install_change)
        self.keyboard = VirtualKeyboard()
        self.reader = ControllerReader(self.config["binding"], self._on_combo, self._on_capture)

        self.lock = threading.RLock()
        self.choice = DisplayChoice(None, "desktop", "Not checked yet")
        self.binary: Optional[str] = None
        self.version: Optional[str] = None
        self.cli: Optional[HexCli] = None
        self.status: dict = {}
        self.status_code = EXIT_NOT_RUNNING
        self.status_at = 0.0
        self.phase = "idle"  # idle | recording | transcribing
        self.pressed_at = 0.0
        self.last_text = ""
        self.last_error = ""
        self.pill_hidden = False

        self.jobs: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self.stopping = threading.Event()
        self.threads: list[threading.Thread] = []

    # -- Lifecycle -------------------------------------------------------------

    def start(self) -> None:
        self.reader.start()
        for target, name in ((self._worker, "hexdeck-dictation"), (self._session_loop, "hexdeck-session")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self.threads.append(thread)

    def stop(self) -> None:
        self.stopping.set()
        self.jobs.put(None)
        self.reader.stop()
        for thread in self.threads:
            thread.join(timeout=5)
        self._restore_pill()
        self.service.stop()
        self.keyboard.close()

    # -- Events ----------------------------------------------------------------

    def emit(self, kind: str, **payload: Any) -> None:
        payload["kind"] = kind
        payload["notify"] = self.config["notifications"]
        try:
            self.emit_event("hexdeck_event", payload)
        except Exception as error:  # pragma: no cover - frontend gone
            logger.debug("emit failed: %s", error)

    def _fail(self, message: str) -> None:
        self.last_error = message
        logger.warning(message)
        self.emit("error", message=message)

    # -- Session loop ----------------------------------------------------------

    def _session_loop(self) -> None:
        while not self.stopping.is_set():
            try:
                self.refresh_session()
            except Exception:  # pragma: no cover - keep the loop alive
                logger.exception("Session check failed")
            self.stopping.wait(SESSION_INTERVAL)

    def refresh_session(self) -> None:
        choice = detect_display(self.account, self.config["display"])
        binary = find_hex(self.account, self.config["hex_path"])
        with self.lock:
            changed = binary != self.binary
            self.choice, self.binary = choice, binary
            if changed:
                self.version = HexCli(self.account, binary).version() if binary else None
        if binary is None:
            self.cli = None
            self._set_status(EXIT_NOT_RUNNING, {})
            return
        cli = HexCli(self.account, binary, choice.display)
        if choice.kind == "gamescope" and choice.display and self.config["enabled"]:
            current = self.service.cli
            retarget = (not self.service.wanted or current is None
                        or current.display != choice.display or current.binary != binary)
            if retarget:
                self.service.budget.reset()
                if self.service.start(cli):
                    self._apply_game_mode_settings()
            elif self.service.external:
                # The Hex we borrowed went away: run our own.
                if not self.service.answers():
                    self.service.external = False
                    self.service.supervise()
                    self._apply_game_mode_settings()
            elif not self.service.owned_running:
                self.service.supervise()
                if self.service.owned_running:
                    self._apply_game_mode_settings()
            if self.service.error and self.service.error != self.last_error:
                self._fail(self.service.error)
            self.cli = self.service.cli or cli
        else:
            # Desktop Mode, or HexDeck disabled: never run a Hex of our own;
            # the controller still drives the user's Hex if one is running.
            if self.service.wanted:
                self._restore_pill()
                self.service.stop()
            self.cli = cli
        self.refresh_status(force=True)

    def _apply_game_mode_settings(self) -> None:
        """Hide Hex's recording pill while HexDeck owns Hex in Game Mode."""
        cli = self.service.cli
        if not self.config["hide_hex_pill"] or self.service.external or cli is None \
                or not self.service.owned_running:
            return
        current = setting_value(cli.get_setting("indicator_position").reply, "indicator_position")
        if current and current != "hidden":
            self.config.set("saved_indicator_position", current)
        if current != "hidden" and cli.set_setting("indicator_position", "hidden").ok:
            self.pill_hidden = True

    def _restore_pill(self) -> None:
        saved = self.config["saved_indicator_position"]
        cli = self.service.cli
        if saved and cli is not None and (self.pill_hidden or self.service.owned_running):
            if cli.set_setting("indicator_position", saved).ok:
                self.config.set("saved_indicator_position", None)
                self.pill_hidden = False

    def refresh_status(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.status_at < STATUS_MAX_AGE:
            return
        cli = self.cli
        if cli is None:
            return
        result = cli.status()
        self._set_status(result.code, result.reply if result.ok else {})

    def _set_status(self, code: int, reply: dict) -> None:
        with self.lock:
            self.status_code, self.status, self.status_at = code, reply, time.monotonic()

    # -- Controller ------------------------------------------------------------

    def _on_combo(self, edge: str) -> None:
        if not self.config["enabled"]:
            return
        now = time.monotonic()
        if self.config["trigger_mode"] == "toggle":
            if edge == "press":
                self.jobs.put(("toggle",))
            return
        if edge == "press":
            self.pressed_at = now
            self.jobs.put(("start",))
        else:
            held_ms = (now - self.pressed_at) * 1000
            self.jobs.put(("cancel",) if held_ms < self.config["min_hold_ms"] else ("stop",))

    def _on_capture(self, snapshot: dict) -> None:
        if snapshot.get("phase") == "captured" and snapshot.get("buttons"):
            self.set_config("binding", snapshot["buttons"])
            self.emit("binding", buttons=self.config["binding"])

    # -- Dictation worker ------------------------------------------------------

    def _worker(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            try:
                getattr(self, f"_job_{job[0]}")(*job[1:])
            except Exception as error:  # pragma: no cover - keep the worker alive
                logger.exception("Dictation job %s failed", job[0])
                self._fail(f"Dictation failed: {error}")

    def _require_cli(self) -> Optional[HexCli]:
        cli = self.cli
        if cli is None:
            self._fail("Install Hex first")
        return cli

    def _job_start(self) -> None:
        cli = self._require_cli()
        if cli is None:
            return
        result = cli.dictation("start")
        if result.ok:
            self.phase = "recording"
            self.last_error = ""
            self.emit("recording")
        else:
            self._fail(f"Couldn't start dictation: {result.message}")

    def _job_cancel(self) -> None:
        cli = self._require_cli()
        if cli is None:
            return
        cli.dictation("cancel")
        if self.phase == "recording":
            self.phase = "idle"
            self.emit("cancelled")

    def _job_toggle(self) -> None:
        cli = self._require_cli()
        if cli is None:
            return
        status = cli.status()
        recording = (status.reply.get("capture") or {}).get("state") == "recording" if status.ok else False
        if recording or self.phase == "recording":
            self._job_stop()
        else:
            self._job_start()

    def _job_stop(self) -> None:
        cli = self._require_cli()
        if cli is None:
            return
        if self.config["output"] == "type":
            self.phase = "transcribing"
            self.emit("transcribing")
            result = cli.dictation("stop", print_text=True)
            self.phase = "idle"
            self._finish_typed(result)
            return
        result = cli.dictation("stop")
        self.phase = "idle"
        if not result.ok:
            self._fail(f"Couldn't finish dictation: {result.message}")
        elif result.reply.get("status") == "done" and result.reply.get("changed", True) is not False \
                and "discard" not in str(result.reply.get("message", "")).lower():
            # Hex transcribes and pastes on its own from here.
            self.emit("transcribing")
            threading.Thread(target=self._report_pasted, daemon=True).start()
        else:
            self.emit("nothing", message=result.message)

    def _finish_typed(self, result: HexResult) -> None:
        if result.code == EXIT_NO_SPEECH:
            self.emit("nothing", message="No speech heard")
            return
        if not result.ok:
            self._fail(f"Transcription failed: {result.message}")
            return
        text = transcript_text(result.reply).strip()
        if not text:
            self.emit("nothing", message="No speech heard")
            return
        try:
            dropped = self.keyboard.type(text, self.config["press_enter"])
        except OSError as error:
            self._fail(f"Couldn't type the text: {error.strerror or error}")
            return
        self.last_text = text
        self.emit("done", text=text, dropped=dropped)

    def _report_pasted(self) -> None:
        """Wait for Hex to finish, then show what it pasted."""
        cli = self.cli
        if cli is None:
            return
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not self.stopping.is_set():
            status = cli.status()
            capture = status.reply.get("capture") or {} if status.ok else {}
            if capture.get("state") == "idle" and not capture.get("pending_jobs"):
                break
            time.sleep(0.4)
        history = cli.run("history", "--limit", "1", timeout=10)
        text = last_history_text(history.reply) if history.ok else ""
        if text:
            self.last_text = text
        self.emit("done", text=text)

    # -- RPC: state ------------------------------------------------------------

    def get_state(self) -> dict:
        self.refresh_status()
        with self.lock:
            status = self.status
            hex_state = {
                "installed": self.binary is not None,
                "path": self.binary,
                "version": self.version,
                "running": self.status_code == EXIT_OK,
                "owned": self.service.owned_running,
                "external": self.service.external,
                "service_error": self.service.error,
                "listener": (status.get("listener") or {}).get("status", ""),
                "capture": (status.get("capture") or {}).get("state", ""),
                "model": status.get("model") or {},
                "log": self.service.log_path,
            }
        return {
            "version": VERSION,
            "config": self.config.public(),
            "session": {"kind": self.choice.kind, "display": self.choice.display, "reason": self.choice.reason},
            "hex": hex_state,
            "controller": self.reader.snapshot(),
            "install": self.installer.snapshot(),
            "phase": self.phase,
            "last_text": self.last_text,
            "last_error": self.last_error,
            "keyboard_shortcuts": [{"value": value, "label": label} for value, label in KEYBOARD_SHORTCUTS],
        }

    def set_config(self, key: str, value: Any) -> dict:
        stored = self.config.set(key, value)
        if key == "binding":
            self.reader.set_binding(stored)
        if key in ("enabled", "display", "hex_path"):
            threading.Thread(target=self.refresh_session, daemon=True).start()
        if key == "hide_hex_pill" and self.service.owned_running:
            if stored:
                self._apply_game_mode_settings()
            else:
                self._restore_pill()
        return {"key": key, "value": stored}

    # -- RPC: Hex --------------------------------------------------------------

    def _cli_or_raise(self) -> HexCli:
        if self.cli is None:
            raise RuntimeError("Hex isn't installed")
        return self.cli

    @staticmethod
    def _answer(result: HexResult) -> dict:
        if result.ok:
            return {"ok": True, "message": result.message if result.reply.get("message") else "", "reply": result.reply}
        return {"ok": False, "error": result.message}

    def list_models(self) -> dict:
        result = self._cli_or_raise().models()
        if not result.ok:
            return {"ok": False, "error": result.message, "models": []}
        models = result.reply.get("models") or []
        return {"ok": True, "models": [{**m, **language_info(m)} for m in models if isinstance(m, dict)]}

    def remove_model(self, model_id: str) -> dict:
        """Delete a downloaded model's files (see ``model_files``)."""
        cli = self._cli_or_raise()
        models = self.list_models().get("models", [])
        model = next((m for m in models if m.get("id") == model_id), None)
        if model is None:
            return {"ok": False, "error": f"Hex has no model {model_id}"}
        name = model.get("name") or model_id
        if not model.get("installed"):
            return {"ok": False, "error": f"{name} isn't downloaded"}
        self.refresh_status(force=True)
        with self.lock:
            report = dict(self.status.get("model") or {})
        fallback = report.get("fallback") if isinstance(report.get("fallback"), dict) else {}
        if model.get("selected") or model_id in (report.get("id"), fallback.get("id")):
            return {"ok": False, "error": f"{name} is the model Hex uses. Choose another one first."}
        if report.get("preparing"):
            return {"ok": False, "error": "A model download is in progress. Try again when it finishes."}
        source = str(model.get("source") or "")
        if source.startswith("found"):
            return {"ok": False, "error": f"{name} belongs to another app ({source[6:].strip()}); HexDeck leaves it alone"}
        if model_id.startswith("custom-") or source == "imported":
            answer = self._answer(cli.remove_import(model_id))
        else:
            status = cli.model_status(model_id)
            found = model_file(status.reply) if status.ok else None
            if found is None:
                return {"ok": False, "error": status.message if not status.ok else "Hex didn't say where the model is"}
            try:
                remove_model_files(found[1], cli.account.home)
            except RemoveError as error:
                return {"ok": False, "error": str(error)}
            answer = {"ok": True}
        if answer["ok"]:
            logger.info("removed model %s", model_id)
            answer["message"] = f"Deleted {name}"
        return answer

    def select_model(self, model_id: str, language: str = "") -> dict:
        cli = self._cli_or_raise()
        models = self.list_models().get("models", [])
        model = next((m for m in models if m.get("id") == model_id), None)
        if model is None:
            return {"ok": False, "error": f"Hex has no model {model_id}"}
        result = cli.use_model(model_id, language) if model.get("installed") else cli.install_model(model_id, language)
        self.refresh_status(force=True)
        answer = self._answer(result)
        answer["downloading"] = not model.get("installed")
        return answer

    def cancel_model_download(self) -> dict:
        return self._answer(self._cli_or_raise().cancel_model())

    def get_hex_settings(self) -> dict:
        cli = self._cli_or_raise()
        values = {}
        for key in ("dictation_hotkey", "sound_effects", "transcription_device"):
            result = cli.get_setting(key)
            values[key] = setting_value(result.reply, key) if result.ok else None
        return {"ok": True, "settings": values}

    def set_hex_setting(self, key: str, value: str) -> dict:
        if key not in ("dictation_hotkey", "sound_effects", "transcription_device"):
            return {"ok": False, "error": f"HexDeck doesn't change {key}"}
        return self._answer(self._cli_or_raise().set_setting(key, value))

    def install_hex(self) -> dict:
        if not self.installer.start():
            return {"ok": False, "error": "An install is already running"}
        return {"ok": True}

    def _on_install_change(self) -> None:
        snapshot = self.installer.snapshot()
        if snapshot["state"] == "done":
            self.emit("installed", version=snapshot["version"])
            threading.Thread(target=self.refresh_session, daemon=True).start()
        elif snapshot["state"] == "failed":
            self._fail(snapshot["error"])

    def take_over_hex(self) -> dict:
        """Quit a Hex HexDeck didn't start and run one on Game Mode's display."""
        if self.binary is None or self.choice.kind != "gamescope" or not self.choice.display:
            return {"ok": False, "error": "Only available in Game Mode with Hex installed"}
        ok = self.service.take_over(HexCli(self.account, self.binary, self.choice.display))
        if ok:
            self._apply_game_mode_settings()
        self.cli = self.service.cli
        self.refresh_status(force=True)
        return {"ok": ok, "error": self.service.error}

    def restart_hex(self) -> dict:
        self._restore_pill()
        self.service.stop()
        self.service.budget.reset()
        self.refresh_session()
        return {"ok": self.status_code == EXIT_OK, "error": self.service.error}

    def test_dictation(self, seconds: float = 4.0) -> dict:
        """Record for ``seconds`` and return the transcript without pasting."""
        cli = self._cli_or_raise()
        seconds = max(1.0, min(10.0, float(seconds)))
        started = cli.dictation("start")
        if not started.ok:
            return {"ok": False, "error": started.message}
        self.emit("recording")
        time.sleep(seconds)
        result = cli.dictation("stop", print_text=True)
        if result.code == EXIT_NO_SPEECH:
            self.emit("nothing", message="No speech heard")
            return {"ok": True, "text": ""}
        if not result.ok:
            return {"ok": False, "error": result.message}
        text = transcript_text(result.reply)
        self.last_text = text
        return {"ok": True, "text": text}

    # -- RPC: binding capture --------------------------------------------------

    def start_binding_capture(self) -> dict:
        return self.reader.start_capture()

    def get_binding_capture(self) -> Optional[dict]:
        return self.reader.capture_snapshot()

    def cancel_binding_capture(self) -> None:
        self.reader.cancel_capture()

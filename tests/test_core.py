import os
import shutil
import stat
import sys
import time

import pytest

from hexdeck import core as core_module
from hexdeck.core import HexDeck, last_history_text
from hexdeck.hexcli import HexCli
from hexdeck.service import HexService
from hexdeck.session import Account, DisplayChoice

FAKE = os.path.join(os.path.dirname(__file__), "fake_hex.py")


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    binary = home / ".local" / "bin" / "hex"
    binary.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    yield home
    pid = home / "service.pid"
    if pid.exists():
        pid.unlink()


@pytest.fixture
def account(home):
    return Account(os.environ.get("USER", "me"), os.getuid(), os.getgid(), str(home))


def calls(home):
    path = home / "calls.log"
    return path.read_text().splitlines() if path.exists() else []


class FakeKeyboard:
    def __init__(self):
        self.typed = []

    def type(self, text, press_enter=False):
        self.typed.append((text, press_enter))
        return 0

    def close(self):
        pass


@pytest.fixture
def deck(tmp_path, account, monkeypatch):
    events = []
    monkeypatch.setattr(core_module, "detect_display",
                        lambda _account, _override: DisplayChoice(":1", "gamescope", "test"))
    deck = HexDeck(str(tmp_path / "settings"), str(tmp_path / "logs"),
                   emit=lambda _name, payload: events.append(payload), account=account)
    deck.keyboard = FakeKeyboard()
    deck.events = events
    yield deck
    deck.service.stop()


def drain(deck):
    while not deck.jobs.empty():
        job = deck.jobs.get()
        getattr(deck, f"_job_{job[0]}")(*job[1:])


def kinds(deck):
    return [event["kind"] for event in deck.events]


def test_service_starts_hex_on_the_gamescope_display_and_hides_the_pill(deck, home):
    deck.refresh_session()
    assert deck.service.owned_running
    assert deck.status_code == 0
    assert "service DISPLAY=:1" in calls(home)
    assert "settings set indicator_position hidden DISPLAY=:1" in calls(home)
    assert deck.config["saved_indicator_position"] == "top"
    deck.stop()
    assert not deck.service.owned_running
    assert "settings set indicator_position top DISPLAY=:1" in calls(home)


def test_uses_an_already_running_hex(account, home, tmp_path):
    first = HexService(account, str(tmp_path / "a.log"))
    assert first.start(HexCli(account, str(home / ".local/bin/hex"), ":1"))
    second = HexService(account, str(tmp_path / "b.log"))
    assert second.start(HexCli(account, str(home / ".local/bin/hex"), ":1"))
    assert second.external and not second.owned_running
    first.stop()


def test_service_is_restarted_after_a_crash(deck, home):
    deck.refresh_session()
    os.kill(deck.service.process.pid, 9)
    deck.service.process.wait()
    (home / "service.pid").unlink()
    deck.refresh_session()
    assert deck.service.owned_running
    assert calls(home).count("service DISPLAY=:1") == 2


def test_hold_to_dictate_pastes_through_hex(deck, home):
    deck.refresh_session()
    deck._on_combo("press")
    deck.pressed_at -= 1  # held for a second
    deck._on_combo("release")
    drain(deck)
    assert "dictation start DISPLAY=:1" in calls(home)
    assert "dictation stop DISPLAY=:1" in calls(home)
    assert kinds(deck)[:2] == ["recording", "transcribing"]


def test_a_tap_shorter_than_the_minimum_is_cancelled(deck, home):
    deck.refresh_session()
    deck._on_combo("press")
    deck._on_combo("release")
    drain(deck)
    assert "dictation cancel DISPLAY=:1" in calls(home)
    assert "dictation stop DISPLAY=:1" not in calls(home)


def test_type_mode_types_the_transcript(deck, home):
    deck.refresh_session()
    deck.set_config("output", "type")
    deck.set_config("press_enter", True)
    deck._on_combo("press")
    deck.pressed_at -= 1
    deck._on_combo("release")
    drain(deck)
    assert "dictation stop --print DISPLAY=:1" in calls(home)
    assert deck.keyboard.typed == [("Hello from Hex.", True)]
    assert deck.events[-1]["kind"] == "done"
    assert deck.events[-1]["text"] == "Hello from Hex."


def test_toggle_mode(deck, home):
    deck.refresh_session()
    deck.set_config("trigger_mode", "toggle")
    deck._on_combo("press")
    deck._on_combo("release")
    drain(deck)
    assert deck.phase == "recording"
    deck._on_combo("press")
    drain(deck)
    assert "dictation stop DISPLAY=:1" in calls(home)


def test_disabled_ignores_the_controller(deck, home):
    deck.refresh_session()
    deck.config.set("enabled", False)
    deck._on_combo("press")
    assert deck.jobs.empty()


def test_model_selection_uses_installed_models_and_installs_others(deck, home):
    deck.refresh_session()
    models = deck.list_models()["models"]
    assert [m["id"] for m in models] == ["parakeet_v3", "whisper_large_v3_turbo"]
    assert deck.select_model("parakeet_v3", "de")["ok"]
    assert "model use parakeet_v3 --language de DISPLAY=:1" in calls(home)
    answer = deck.select_model("whisper_large_v3_turbo")
    assert answer["ok"] and answer["downloading"]
    assert "model install whisper_large_v3_turbo DISPLAY=:1" in calls(home)
    assert not deck.select_model("nope")["ok"]


def test_keyboard_shortcut_goes_to_hex(deck, home):
    deck.refresh_session()
    assert deck.set_hex_setting("dictation_hotkey", "f9")["ok"]
    assert deck.get_hex_settings()["settings"]["dictation_hotkey"] == "f9"
    assert not deck.set_hex_setting("history_retention", "off")["ok"]


def test_binding_capture_saves_the_new_binding(deck):
    deck._on_capture({"phase": "captured", "buttons": ["R5"]})
    assert deck.config["binding"] == ["R5"]
    assert deck.reader.detector.binding == {"R5"}


def test_state_snapshot(deck):
    deck.refresh_session()
    state = deck.get_state()
    assert state["hex"]["installed"] and state["hex"]["running"] and state["hex"]["owned"]
    assert state["hex"]["version"] == "3.4.0"
    assert state["hex"]["listener"] == "Listening"
    assert state["session"]["kind"] == "gamescope"


def test_desktop_mode_never_starts_hex(deck, home, monkeypatch):
    monkeypatch.setattr(core_module, "detect_display",
                        lambda _account, _override: DisplayChoice(":0", "desktop", "test"))
    deck.refresh_session()
    assert not deck.service.owned_running
    assert not any(line.startswith("service") for line in calls(home))


def test_last_history_text():
    assert last_history_text({"entries": [{"text": "hi"}]}) == "hi"
    assert last_history_text({"value": [{"final": "yo"}]}) == "yo"
    assert last_history_text({}) == ""

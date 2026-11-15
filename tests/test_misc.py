import json

import pytest

from hexdeck.config import DEFAULTS, Config
from hexdeck.hexcli import HexResult, parse_reply, setting_value
from hexdeck.service import RestartBudget
from hexdeck.session import Account, choose_display, parse_server_id, user_environment, x_displays
from hexdeck.typer import KEY_ENTER, KEY_LEFTSHIFT, key_sequence, to_typeable


# -- typer ---------------------------------------------------------------------

def test_typeable_folds_punctuation_and_accents():
    assert to_typeable("It’s “fine” — ok…") == ("It's \"fine\" - ok...", 0)
    assert to_typeable("mañana café") == ("manana cafe", 0)
    assert to_typeable("при hi") == (" hi", 3)


def test_newlines_never_press_enter():
    text, _ = to_typeable("one\ntwo")
    assert all(code != KEY_ENTER for code, _ in key_sequence(text))


def test_key_sequence_shifts_capitals_and_presses_enter_on_request():
    events = key_sequence("Hi!", press_enter=True)
    assert events[0] == (KEY_LEFTSHIFT, 1)
    assert events[-2:] == [(KEY_ENTER, 1), (KEY_ENTER, 0)]
    presses = [code for code, value in events if value == 1]
    assert presses.count(KEY_LEFTSHIFT) == 2


# -- config --------------------------------------------------------------------

def test_config_round_trip_and_validation(tmp_path):
    path = tmp_path / "settings.json"
    config = Config(str(path))
    assert config["binding"] == DEFAULTS["binding"]
    config.set("binding", ["R5", "L5"])
    config.set("output", "type")
    with pytest.raises(ValueError):
        config.set("output", "shout")
    with pytest.raises(ValueError):
        config.set("display", "localhost:0")
    again = Config(str(path))
    assert again["binding"] == ["L5", "R5"]
    assert again["output"] == "type"


def test_config_ignores_bad_saved_values(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"binding": ["Nope"], "trigger_mode": "toggle", "junk": 1}))
    config = Config(str(path))
    assert config["binding"] == DEFAULTS["binding"]
    assert config["trigger_mode"] == "toggle"


# -- hex CLI parsing ------------------------------------------------------------

def test_parse_reply_tolerates_log_lines():
    assert parse_reply('{"version": 4, "status": "done"}')["status"] == "done"
    assert parse_reply('warning: something\n{"status": "models", "models": []}')["status"] == "models"
    assert parse_reply("hex 3.4.0") == {"message": "hex 3.4.0"}
    assert parse_reply("") == {}


def test_result_messages():
    assert HexResult(3).message == "Hex isn't running"
    assert HexResult(1, {"message": "Busy"}).message == "Busy"
    assert HexResult(1, {}, "error: boom\n").message == "error: boom"


def test_setting_value():
    reply = {"status": "settings", "settings": [{"key": "sound_effects", "value": True}]}
    assert setting_value(reply, "sound_effects") is True
    assert setting_value(reply, "dictation_hotkey") is None


# -- session -------------------------------------------------------------------

ACCOUNT = Account("deck", 1000, 1000, "/home/deck")


def test_user_environment_pins_hex_to_x11():
    env = user_environment(ACCOUNT, ":1")
    assert env["DISPLAY"] == ":1"
    assert env["XDG_SESSION_TYPE"] == "x11"
    assert "WAYLAND_DISPLAY" not in env
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"
    assert env["HOME"] == "/home/deck"


def test_server_id_parsing():
    assert parse_server_id("GAMESCOPE_XWAYLAND_SERVER_ID(CARDINAL) = 0\n") == 0
    assert parse_server_id("GAMESCOPE_XWAYLAND_SERVER_ID:  not found.") is None
    assert parse_server_id(None) is None


def test_choose_display_prefers_gamescope_server_zero():
    ids = {":0": "X(CARDINAL) = 1", ":1": "X(CARDINAL) = 0"}
    choice = choose_display("auto", [":0", ":1"], True, ids.get)
    assert (choice.display, choice.kind) == (":1", "gamescope")


def test_choose_display_falls_back_without_xprop():
    choice = choose_display("auto", [":0", ":1"], True, lambda _display: None)
    assert choice.display == ":1"


def test_choose_display_in_desktop_mode():
    choice = choose_display("auto", [":0"], False, lambda _display: None)
    assert (choice.display, choice.kind) == (":0", "desktop")


def test_choose_display_override():
    choice = choose_display(":2", [":0", ":1"], True, lambda _display: None)
    assert (choice.display, choice.kind) == (":2", "gamescope")


def test_x_displays(tmp_path):
    for name in ("X1", "X0", "X10", "Xfoo"):
        (tmp_path / name).write_text("")
    assert x_displays(str(tmp_path)) == [":0", ":1", ":10"]


# -- service -------------------------------------------------------------------

def test_restart_budget():
    now = [0.0]
    budget = RestartBudget(limit=2, window=10, clock=lambda: now[0])
    assert budget.allow() and budget.allow()
    assert not budget.allow()
    now[0] = 11
    assert budget.allow()


def test_remove_model_files_stays_in_home(tmp_path):
    import pytest
    from hexdeck.model_files import RemoveError, remove_model_files
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "m.gguf").write_text("x")
    with pytest.raises(RemoveError):
        remove_model_files(str(outside / "m.gguf"), str(home))
    with pytest.raises(RemoveError):
        remove_model_files(str(home / "notes.txt"), str(home))
    with pytest.raises(RemoveError):
        remove_model_files("relative.gguf", str(home))
    assert (outside / "m.gguf").exists()


def test_model_file_parses_hex_model_status():
    from hexdeck.hexcli import model_file
    assert model_file({"message": "installed\tverified\tParakeet v3\t/h/.local/share/hex/models/p.gguf"}) == \
        (True, "/h/.local/share/hex/models/p.gguf")
    assert model_file({"message": "missing\tunverified\tX\t/a b/x.gguf"}) == (False, "/a b/x.gguf")
    assert model_file({"message": "nonsense"}) is None


def test_language_info_for_an_unknown_model():
    from hexdeck.languages import language_info
    assert language_info({"id": "custom-1", "languages": ["en", "de"]}) == \
        {"language_mode": "choice", "detects_language": None, "language_choices": ["en", "de"],
         "supported_languages": ["en", "de"]}
    assert language_info({"id": "custom-2", "languages": ["en"]})["language_mode"] == "fixed"


def test_whisper_offers_the_languages_hex_lists_in_hex_order():
    from hexdeck.languages import LISTED_CODES, language_info, language_name
    whisper = language_info({"id": "whisper_large_v3_turbo", "languages": ["*"]})
    assert whisper["supported_languages"] == list(LISTED_CODES) and len(LISTED_CODES) == 42
    assert whisper["language_choices"] == ["auto"] + list(LISTED_CODES)
    # Parakeet v3 hears the language itself, but still says which it knows.
    parakeet = language_info({"id": "parakeet_v3", "languages": ["de", "en", "ru"]})
    assert parakeet["language_choices"] == ["auto"]
    assert parakeet["supported_languages"] == ["en", "de", "ru"]
    # An import's unlisted language comes after the listed ones.
    assert language_info({"id": "custom-3", "languages": ["nn", "en"]})["supported_languages"] == ["en", "nn"]
    assert language_name("zh") == "Mandarin Chinese"
    assert language_name("nn") == "Norwegian Nynorsk"
    assert language_name("xx") == "xx"


def test_model_facts_match_hex_picker():
    from hexdeck.catalog import model_facts
    whisper = model_facts({"id": "whisper_large_v3_turbo"})
    assert whisper["description"] == "Almost any language, and it reads your vocabulary"
    assert whisper["wait"] == "2 s wait"
    assert model_facts({"id": "parakeet_v3"})["wait"] == "Under 1 s wait"
    assert model_facts({"id": "granite_speech_5"})["wait"] == "1 s wait"
    assert model_facts({"id": "nemotron_3_5_asr"})["wait"] == "No wait"
    assert model_facts({"id": "custom-1", "streams": True})["wait"] == "No wait"
    assert model_facts({"id": "custom-1"}) == {"description": "", "wait": None, "wait_seconds": None}


def test_recommendations_follow_hex_routing():
    from hexdeck.catalog import all_recommendations, recommendations
    assert recommendations("auto") == [["whisper_large_v3_turbo", "recommended"], ["qwen3_asr06_b", "fastest"]]
    assert recommendations("en")[0] == ["parakeet_unified_en", "recommended"]
    assert recommendations("ru")[0] == ["gigaam_v3", "recommended"]
    assert recommendations("de")[0] == ["parakeet_v3", "recommended"]  # Parakeet v3's languages
    assert recommendations("th")[0] == ["qwen3_asr06_b", "recommended"]  # Qwen's languages
    assert recommendations("bn") == [["whisper_large_v3_turbo", "recommended"]]
    assert recommendations("sv") == [["whisper_large_v3_turbo", "recommended"], ["parakeet_v3", "fastest"]]
    assert len(all_recommendations()) == 43

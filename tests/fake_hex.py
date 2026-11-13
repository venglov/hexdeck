#!/usr/bin/env python3
"""A stand-in for the ``hex`` executable, driven by files in $HOME.

``hex service`` writes a pid file and sleeps; every other command answers as
the real CLI would (JSON on stdout, Hex's exit codes) and is logged to
``$HOME/calls.log``.
"""

import json
import os
import signal
import sys
import time

home = os.environ["HOME"]
state_path = os.path.join(home, "fake-state.json")
pid_path = os.path.join(home, "service.pid")


models_dir = os.path.join(home, ".local", "share", "hex", "models")

CATALOG = [
    ("parakeet_v3", "Parakeet V3", ["en", "de", "ru"], "478 MB", False),
    ("whisper_large_v3_turbo", "Whisper Large V3 Turbo", ["*"], "1.6 GB", False),
    ("nemotron_3_5_asr", "Nemotron 3.5 ASR", ["en", "de", "ru"], "1.2 GB", True),
    ("parakeet_unified_en", "Parakeet Unified English", ["en"], "731 MB", True),
]


def model_path(model_id):
    return os.path.join(models_dir, model_id + ".gguf")


def install_file(model_id):
    os.makedirs(models_dir, exist_ok=True)
    with open(model_path(model_id), "w") as stream:
        stream.write("gguf")


def load():
    try:
        with open(state_path) as stream:
            return json.load(stream)
    except (OSError, ValueError):
        state = {"recording": False, "model": "parakeet_v3", "language": "en",
                 "settings": {"indicator_position": "top", "sound_effects": True,
                              "dictation_hotkey": "option+space"}}
        install_file("parakeet_v3")
        save(state)
        return state


def save(state):
    with open(state_path, "w") as stream:
        json.dump(state, stream)


def running():
    try:
        with open(pid_path) as stream:
            os.kill(int(stream.read()), 0)
        return True
    except (OSError, ValueError):
        return False


def reply(code, **fields):
    print(json.dumps({"version": 4, **fields}))
    sys.exit(code)


args = [a for a in sys.argv[1:] if a != "--json"]
with open(os.path.join(home, "calls.log"), "a") as log:
    log.write(" ".join(args) + f" DISPLAY={os.environ.get('DISPLAY')}\n")

if args == ["--version"]:
    print("hex 3.4.0")
    sys.exit(0)

if args == ["service"]:
    with open(pid_path, "w") as stream:
        stream.write(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while os.path.exists(pid_path):
        time.sleep(0.05)
    sys.exit(0)

if args[:2] == ["model", "status"]:
    model_id = args[2] if len(args) > 2 else load()["model"]
    if model_id not in [entry[0] for entry in CATALOG]:
        print(f"hex: unknown model {model_id}", file=sys.stderr)
        sys.exit(1)
    present = os.path.exists(model_path(model_id))
    print(f"{'installed' if present else 'missing'}\tunverified\t{model_id}\t{model_path(model_id)}")
    sys.exit(0)
if args[:2] == ["model", "remove"]:
    if not args[2].startswith("custom-"):
        print(f"hex: no imported model is {args[2]}; run `hex model list`", file=sys.stderr)
        sys.exit(1)
    state = load()
    state["extra_models"] = [m for m in state.get("extra_models", []) if m["id"] != args[2]]
    save(state)
    print(f"removed\t{args[2]}")
    sys.exit(0)

if not running():
    reply(3, status="error", code="not-running", message="Hex isn't running")

state = load()
if args == ["status"]:
    reply(0, status="status", listener={"running": True, "status": "Listening"},
          capture={"state": "recording" if state["recording"] else "idle", "pending_jobs": 0},
          model={"id": state["model"], "name": state["model"], "language": state.get("language", "en"),
                 "installed": True, "preparing": state.get("preparing"), "downloaded_bytes": 0})
if args == ["quit", "--force"]:
    os.unlink(pid_path)
    reply(0, status="done", message="Quit", changed=True)
if args[:1] == ["dictation"]:
    action = args[1]
    if action == "start":
        state["recording"] = True
        save(state)
        reply(0, status="done", message="Recording", changed=True)
    if action == "cancel":
        state["recording"] = False
        save(state)
        reply(0, status="done", message="Cancelled", changed=True)
    if action == "stop":
        was = state["recording"]
        state["recording"] = False
        save(state)
        if "--print" in args:
            if not was:
                reply(1, status="error", code="not-recording", message="Nothing is recording")
            reply(0, status="transcript", text="Hello from Hex.")
        reply(0, status="done", message="Transcribing", changed=True)
if args[:2] == ["model", "list"]:
    reply(0, status="models", models=[
        {"id": model_id, "name": name, "languages": languages, "size": size,
         "installed": os.path.exists(model_path(model_id)), "selected": state["model"] == model_id,
         "streams": streams, "source": "hex" if os.path.exists(model_path(model_id)) else "download"}
        for model_id, name, languages, size, streams in CATALOG
    ] + state.get("extra_models", []))
if args[:2] in (["model", "use"], ["model", "install"]):
    state["model"] = args[2]
    if "--language" in args:
        state["language"] = args[args.index("--language") + 1]
    if args[1] == "install":
        install_file(args[2])
    save(state)
    reply(0, status="done", message=f"Using {args[2]}", changed=True)
if args[:2] == ["settings", "get"]:
    key = args[2]
    reply(0, status="settings", settings=[{"key": key, "value": state["settings"].get(key)}])
if args[:2] == ["settings", "set"]:
    state["settings"][args[2]] = args[3]
    save(state)
    reply(0, status="done", message="Saved", changed=True)
if args[:1] == ["history"]:
    reply(0, status="history", entries=[{"text": "Hello from Hex."}])
reply(2, status="error", code="usage", message="unknown command " + " ".join(args))

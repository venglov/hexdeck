# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

HexDeck is a Decky Loader plugin that runs [Hex](https://github.com/anomalyco/hex) (local voice dictation) in Steam Deck Game Mode. The Python backend lives in `main.py` + `py_modules/hexdeck/`, and the React Quick Access panel is in `src/`.

## Git workflow

- PRs into `main` are always squash-merged: `gh pr merge <n> --squash`, and only when the user asks.
- Do all work on the `dev` branch. Squash-merging leaves `dev`'s own commits off `main`, so before starting new work, check whether `dev` has commits that aren't on `main` yet (`git log origin/main..origin/dev`). If it has none, or they've been squash-merged already, reset `dev` to `main`: `git fetch && git checkout dev && git reset --hard origin/main && git push --force-with-lease origin dev`. If an open PR still holds unmerged work, keep building on `dev` as it is.
- Never commit to, push to, or merge into `main` directly. A hook in `.claude/settings.json` blocks `git commit`/`git push` while `main` is checked out, and any push that targets `main`.
- When the work is done, commit to `dev`, push it, and open a PR into `main` (`gh pr create --base main --head dev`). If a PR from `dev` is already open, just push to it.

## Commands

On this machine Node has no global default (it's managed by mise), so prefix npm/npx with `mise exec node@26.12.1 --`.

```sh
npm install
make test                          # python3 -m pytest -q tests
python3 -m pytest -q tests/test_core.py::test_type_mode_types_the_transcript   # one test
make build                         # npm run typecheck && npm run build -> dist/index.js
make package                       # scripts/package.sh -> out/HexDeck.zip (SKIP_BUILD=1 to reuse dist)
make deploy DECK=deck@steamdeck.local   # scp + install into ~/homebrew/plugins, restart plugin_loader
make preview                       # serves the repo; open http://localhost:8765/dev/preview.html
```

The Python code must stay compatible with 3.9, which is what runs the tests locally (Decky itself runs 3.11). Every module uses `from __future__ import annotations`.

## Architecture

- **Hex is never modified or bundled.** In Game Mode, `service.HexService` starts `hex service` (Hex's headless entry point) as the desktop user. HexDeck talks to Hex only through its control CLI (`hex <cmd> --json`, which returns a versioned reply and exits 0 ok / 1 failed / 2 usage / 3 not running / 4 no speech). `hexcli.HexCli` wraps this; don't call Hex's local HTTP API directly.
- **Root vs. user.** Decky runs the backend as root (the `root` flag in `plugin.json`), which is needed for hidraw and `/dev/uinput`. Anything Hex-related must run as the desktop user: `session.find_account`, `process_identity` (drops root via `subprocess user=/group=`) and `user_environment` (a clean env, not root's). `user_environment` sets `XDG_SESSION_TYPE=x11` with no `WAYLAND_DISPLAY` on purpose, so Hex pastes via X11/XTest into Gamescope's Xwayland instead of adopting Gamescope's Wayland socket.
- **Display discovery** (`session.choose_display`): the game display is the X display whose root window has `GAMESCOPE_XWAYLAND_SERVER_ID = 0` (checked with xprop). The fallback is `:1`. If no Gamescope socket exists, it's Desktop Mode, and HexDeck never spawns its own Hex there; it only drives an already-running one.
- **`core.HexDeck`** is the orchestrator, with three threads:
  - the controller reader (`controller.ControllerReader`, which decodes the raw Valve HID report via `deck_hid`, adapted from Decktation) feeds `ComboDetector` and `BindingCapture`;
  - a single dictation worker consumes a job queue (`_job_start/stop/cancel/toggle`), so press and release are serialized;
  - a session loop (every 3 s, `refresh_session`) re-detects the display/binary, (re)starts or supervises the service (with a `RestartBudget`), and refreshes `hex status`.
- **Output modes:** "paste" = `hex dictation stop` (Hex pastes, then the last text comes from `hex history --limit 1`). "type" = `hex dictation stop --print`, then `typer.VirtualKeyboard` (US-layout uinput; transcript newlines are never typed as Enter).
- **Pill handling:** while HexDeck owns Hex in Game Mode it sets Hex's `indicator_position=hidden`, saves the old value in config (`saved_indicator_position`), and restores it on stop or when switching to Desktop Mode.
- **Settings split:** plugin settings (binding, trigger, output, …) are in `config.py`, validated and saved to Decky's settings dir. Hex's settings (model, language, `dictation_hotkey`, `sound_effects`) stay in Hex and are changed only via `hex settings set`/`hex model use|install`; `core.set_hex_setting` allowlists the keys.
- **RPC/events:** `main.Plugin` methods are thin wrappers that run `HexDeck` methods via `asyncio.to_thread`. Each must have a matching `callable("name")` in `src/api.ts`. The backend emits `hexdeck_event` (`kind`: recording/transcribing/done/nothing/error/installed/binding), which `src/index.tsx` turns into toasts. The panel polls `get_state` every second.
- **Installer** (`installer.py`) mirrors Hex's official `install-linux.sh`: manifest from `anoma.ly/release/hex/desktop/{stable,dev}.json`, then URL/size/SHA-256 checks, then Ed25519 verification (pure Python, `ed25519.py`, tested with RFC 8032 vectors) against Hex's release key, then `~/.local/bin/hex` owned by the user. Downloads use curl as the user.

## Testing

`tests/fake_hex.py` stands in for the `hex` executable (state in `$HOME/fake-state.json`; every call is logged to `$HOME/calls.log` along with its `DISPLAY`). `tests/test_core.py` runs the real service, CLI and dictation flow against it as subprocesses, monkeypatching `core.detect_display`. When you add a Hex command, extend the fake.

`dev/preview.html` renders the built `dist/index.js` with React from a CDN, stand-ins for `@decky/ui`, and a mock backend behind the `@decky/api` loader hook. Add any new RPC to its `backend` object.

## Releases

`out/` and `dist/` are gitignored. Releases are GitHub releases with `out/HexDeck.zip` attached (`gh release create vX.Y.Z out/HexDeck.zip`). Keep the version in sync across `package.json` and `py_modules/hexdeck/__init__.py`.

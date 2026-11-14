![HexDeck](assets/hexdeck-banner.webp)

# HexDeck

Local voice dictation in Steam Deck **Game Mode**, powered by
[Hex](https://github.com/anomalyco/hex). Hold a controller binding, speak,
let go, and the text lands in the game or text field you're in. Everything is
transcribed on the Deck.

From the Quick Access Menu (`...` → HexDeck) you can:

- **pick Hex's speech model** (Parakeet, Whisper, …) and its language from
  one list: the model in use and your other downloaded models come first,
  then **More models**, with Hex's picks for your language first
  (*Recommended*, *Fastest*, …). Each model shows Hex's one-line
  description, how long you wait for the text, and its size; open one to see
  every language it understands and to use, download or delete it. Models
  download in the background, with progress;
- set the language inside the model in use, where the model takes one
  (Whisper, Nemotron, Qwen3-ASR, …, with **Automatic (detect)** first);
  models like Parakeet v3 that hear the language themselves, or know only
  one, have no setting;
- **change the dictation binding**: any 1–4 controller buttons, captured by
  holding them (default **L4 + R4**, the two back grips), and choose
  *Hold to talk* or *Press to start and stop*;
- choose how text arrives: **Pasting (Hex)**, any language, or **Typing
  (US keyboard)** for games that ignore paste, optionally pressing Enter;
- install Hex, test dictation, and turn sounds and notifications on or off;
- under **Advanced**, set **Hex's keyboard shortcut** for an external keyboard.

## Install

Needs [Decky Loader](https://decky.xyz/).

1. Build the archive (below) or download `HexDeck.zip`.
2. Decky Settings → Developer → **Install Plugin from ZIP**.
3. Open HexDeck in the Quick Access Menu. If Hex isn't installed, select
   **Install Hex**: HexDeck downloads the official Linux build into
   `~/.local/bin/hex`, checking its size, SHA-256 and Ed25519 release
   signature exactly as Hex's own installer does.
4. Under **Speech model**, open a model and choose **Download … and use**. It
   downloads (about 0.25–2.4 GB); dictation is ready when the status says *Listening*.
5. Focus a text field, hold **L4 + R4**, speak, let go.

An existing Hex install in `~/.local/bin/hex` (from Hex's install script) is
used as is, with its settings and models.

## How it works

```
 controller (hidraw) ──► HexDeck backend (Decky, root) ──► hex dictation start/stop
                              │  runs as the deck user        │
                              └─► hex service  ◄──────────────┘
                                   on Gamescope's Xwayland: records, transcribes, pastes
```

- **Hex runs unmodified.** In Game Mode HexDeck starts `hex service` (Hex's
  headless entry point, the one its systemd unit uses) as the desktop user,
  on Gamescope's main Xwayland display (found through
  `GAMESCOPE_XWAYLAND_SERVER_ID`), pinned to X11 so Hex's paste (X11
  clipboard + XTest Ctrl+V) reaches games running under Xwayland. It
  restarts Hex if it crashes, and quits it when the plugin unloads.
- **Everything goes through Hex's control CLI** (`hex status`,
  `hex dictation start|stop|cancel`, `hex model list|use|install|cancel`,
  `hex settings get|set`), Hex's stable, versioned contract, documented in
  Hex's `docs/cli.md`. The one exception is **deleting a downloaded model**:
  Hex's Linux CLI can't do it yet, so HexDeck asks `hex model status <id>`
  where the file is and deletes it the way Hex's macOS Settings do (taking
  Hex's download lock, never while a download runs or for the model in use).
- **Streaming models** (Parakeet Unified English, Nemotron 3.5 ASR)
  transcribe while you hold the binding on the Deck's GPU, so text arrives
  sooner after you let go. Hex still inserts the text only once you've
  finished; words don't appear live in the game.
- **The binding is read from the physical controller**, from the Deck's raw
  HID reports (adapted from [Decktation](https://github.com/silverfoxy/decktation)),
  so it works whatever Steam Input layout the game uses. Games still see the
  buttons, which is why the default uses the back grips.
- **Typing mode** asks Hex for the transcript (`hex dictation stop --print`)
  and types it on a virtual uinput keyboard the plugin creates. Only
  characters on a US keyboard can be typed; accents are stripped and other
  characters skipped. A newline in a transcript never presses Enter.
- **Desktop Mode:** HexDeck never starts a Hex of its own there; the
  binding still drives your desktop Hex if it's running.
- While HexDeck runs Hex in Game Mode it hides Hex's recording pill (Steam
  toasts show the state instead) and restores the setting afterwards.

Hex's own settings (model, language, sounds, shortcut) live in Hex's
`settings.json` and are shared with Desktop Mode. HexDeck's settings
(binding, trigger, output) are in Decky's settings folder.

## Troubleshooting

- **Status says "Hex was already running"**: a Hex started outside HexDeck
  answers (for example your desktop Hex's systemd unit). HexDeck uses it; if
  text doesn't reach games, select **Run Hex for Game Mode**.
- **Nothing is pasted in a game**: try **Insert text by → Typing**, or pick
  the display under **Advanced → Game display**.
- **Logs**: Hex's output is in the path shown under Advanced (`hex-service.log`
  in Decky's log folder for HexDeck); the plugin logs to Decky's plugin log.
  `hex status` and `hex logs -n 40` in Desktop Mode's terminal also work.

## Development

```sh
npm install
make test       # Python unit tests, including a fake `hex` executable
make build      # typecheck and bundle dist/index.js
make package    # out/HexDeck.zip
make deploy DECK=deck@steamdeck.local   # copy to a Deck over SSH, restart Decky
make preview    # http://localhost:8765/dev/preview.html: the panel with a mock backend
```

Layout:

| Path | What |
| --- | --- |
| `main.py` | Decky entry point; RPC methods run in worker threads |
| `py_modules/hexdeck/core.py` | Session loop, dictation worker, RPC implementations |
| `py_modules/hexdeck/service.py` | Starts and supervises `hex service` |
| `py_modules/hexdeck/hexcli.py` | Runs `hex … --json` as the desktop user |
| `py_modules/hexdeck/session.py` | Desktop account, environment, Gamescope display discovery |
| `py_modules/hexdeck/controller.py`, `deck_hid.py` | Controller reader, combo detection, binding capture |
| `py_modules/hexdeck/languages.py`, `catalog.py` | What Hex's picker says about each model (languages, descriptions, wait, picks), mirrored from Hex |
| `py_modules/hexdeck/installer.py`, `ed25519.py` | Verified Hex install |
| `py_modules/hexdeck/typer.py` | uinput virtual keyboard |
| `src/` | Quick Access panel (React, `@decky/ui`) |

### Not yet verified on hardware

The unit tests cover the logic, and the panel has been exercised against a
mock backend, but these need a Steam Deck to confirm:

- Hex's X11 paste into games under Gamescope's Xwayland;
- the uinput keyboard being picked up by Gamescope;
- Hex's microphone and Vulkan inference as the `deck` user from Decky;
- the installer against the live release server.

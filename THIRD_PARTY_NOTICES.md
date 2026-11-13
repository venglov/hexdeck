# Third-party notices

## Decktation

`py_modules/hexdeck/deck_hid.py` adapts the Steam Deck HID report decoding,
and `py_modules/hexdeck/controller.py` the binding-capture approach, from
[Decktation](https://github.com/silverfoxy/decktation).

MIT License, Copyright (c) 2026 silverfoxy.

## Hex

HexDeck runs [Hex](https://github.com/anomalyco/hex), which it downloads
separately from Hex's official release server; Hex is not bundled. The
installer mirrors the verification in Hex's `install-linux.sh`, including its
Ed25519 release key.

MIT License, Copyright (c) 2026 Christopher Langton.

## Decky Loader

The frontend uses `@decky/ui` and `@decky/api` from
[Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader); see those
packages for their license terms.

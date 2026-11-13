"""Decode Valve's raw 64-byte controller state reports.

Adapted from Decktation (MIT, https://github.com/silverfoxy/decktation),
whose offsets mirror ``ID_CONTROLLER_STATE`` / ``ID_CONTROLLER_DECK_STATE``
in Linux's ``drivers/hid/hid-steam.c``. Reading the physical HID reports
bypasses Steam Input, so a binding keeps working whatever layout the game
uses, including layouts that emit keyboard and mouse events.
"""

from __future__ import annotations

import glob
import os
from typing import Iterator, Optional

# Button name -> (byte offset, bit offset).
STEAM_DECK_BUTTON_BITS = {
    "A": (8, 7),
    "B": (8, 5),
    "X": (8, 6),
    "Y": (8, 4),
    "L1": (8, 3),
    "R1": (8, 2),
    "L2": (8, 1),
    "R2": (8, 0),
    "L4": (13, 1),
    "R4": (13, 2),
    "L5": (9, 7),
    "R5": (10, 0),
    "L3": (10, 6),
    "R3": (11, 2),
    "View": (9, 4),
    "Menu": (9, 6),
    "D-pad Up": (9, 0),
    "D-pad Right": (9, 1),
    "D-pad Left": (9, 2),
    "D-pad Down": (9, 3),
    "Left Trackpad": (10, 1),
    "Right Trackpad": (10, 2),
}
BUTTONS = tuple(STEAM_DECK_BUTTON_BITS)

# Analog trigger values count as pressed at half pull.
STEAM_DECK_TRIGGER_OFFSETS = {"L2": 44, "R2": 46}
STEAM_DECK_TRIGGER_THRESHOLD = 16384
REPORT_SIZE = 64
DECK_REPORT_TYPE = 9
STEAM_CONTROLLER_REPORT_TYPE = 1

STEAM_CONTROLLER_BUTTON_BITS = {
    name: location for name, location in STEAM_DECK_BUTTON_BITS.items()
    if name not in ("L4", "R4", "R3")
}
STEAM_CONTROLLER_TRIGGER_OFFSETS = {"L2": 11, "R2": 12}
STEAM_CONTROLLER_TRIGGER_THRESHOLD = 128

VALVE_VENDOR = 0x28DE
# product id -> interface suffixes of the controller-state hidraw node
CONTROLLERS = {
    0x1205: ("/input2",),            # Steam Deck
    0x1102: ("/input2",),            # Steam Controller, wired
    0x1142: ("/input1", "/input2"),  # Steam Controller, wireless dongle
}


def button_states(report: bytes) -> Optional[dict]:
    """Physical button states, or ``None`` for a report that isn't state."""
    if len(report) != REPORT_SIZE or report[0] != 1 or report[1] != 0:
        return None
    kind = report[2]
    if kind == DECK_REPORT_TYPE:
        bits, triggers, threshold = STEAM_DECK_BUTTON_BITS, STEAM_DECK_TRIGGER_OFFSETS, STEAM_DECK_TRIGGER_THRESHOLD
    elif kind == STEAM_CONTROLLER_REPORT_TYPE:
        bits, triggers, threshold = (STEAM_CONTROLLER_BUTTON_BITS, STEAM_CONTROLLER_TRIGGER_OFFSETS,
                                     STEAM_CONTROLLER_TRIGGER_THRESHOLD)
    else:
        return None
    states = {name: bool(report[byte] & (1 << bit)) for name, (byte, bit) in bits.items()}
    for name, offset in triggers.items():
        if kind == DECK_REPORT_TYPE:
            value = int.from_bytes(report[offset:offset + 2], "little")
        else:
            value = report[offset]
        states[name] = states[name] or value >= threshold
    return states


def disconnect_report(report: bytes) -> bool:
    """The wireless receiver says its controller went away."""
    return len(report) >= 5 and report[:3] == b"\x01\x00\x03" and report[4] == 1


def _uevent(path: str) -> dict:
    with open(path) as stream:
        return dict(line.rstrip("\n").split("=", 1) for line in stream if "=" in line)


def find_controllers(dev_glob: str = "/dev/hidraw*", sysfs: str = "/sys/class/hidraw") -> Iterator[str]:
    """hidraw nodes carrying a Valve controller's state reports."""
    for node in sorted(glob.glob(dev_glob)):
        try:
            properties = _uevent(os.path.join(sysfs, os.path.basename(node), "device", "uevent"))
            bus, vendor, product = (int(part, 16) for part in properties.get("HID_ID", "").split(":"))
        except (OSError, ValueError):
            continue
        if bus != 3 or vendor != VALVE_VENDOR or product not in CONTROLLERS:
            continue
        if properties.get("HID_PHYS", "").endswith(CONTROLLERS[product]):
            yield node

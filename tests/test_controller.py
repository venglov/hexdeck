import os

import pytest

from hexdeck.controller import BindingCapture, ComboDetector, normalize_binding
from hexdeck.deck_hid import button_states, disconnect_report, find_controllers


def deck_report(*buttons, l2=0, r2=0):
    report = bytearray(64)
    report[0], report[1], report[2] = 1, 0, 9
    bits = {"A": (8, 7), "B": (8, 5), "L1": (8, 3), "R1": (8, 2), "L4": (13, 1), "R4": (13, 2),
            "L5": (9, 7), "R5": (10, 0), "View": (9, 4), "Menu": (9, 6)}
    for name in buttons:
        byte, bit = bits[name]
        report[byte] |= 1 << bit
    report[44:46] = l2.to_bytes(2, "little")
    report[46:48] = r2.to_bytes(2, "little")
    return bytes(report)


def held(report):
    return frozenset(name for name, down in button_states(report).items() if down)


def test_decodes_deck_buttons_and_back_grips():
    assert held(deck_report("L4", "R4")) == {"L4", "R4"}
    assert held(deck_report("A", "L1")) == {"A", "L1"}
    assert held(deck_report()) == frozenset()


def test_half_pulled_trigger_counts_as_pressed():
    assert "L2" in held(deck_report(l2=20000))
    assert "R2" not in held(deck_report(r2=1000))


def test_ignores_non_state_reports():
    assert button_states(b"\x01\x00\x09" + bytes(10)) is None
    other = bytearray(deck_report("A"))
    other[2] = 4
    assert button_states(bytes(other)) is None


def test_disconnect_report():
    assert disconnect_report(b"\x01\x00\x03\x00\x01")
    assert not disconnect_report(deck_report())


def test_finds_the_deck_controller_interface(tmp_path):
    dev = tmp_path / "dev"
    sysfs = tmp_path / "sys"
    dev.mkdir()
    for name, product, phys in (("hidraw0", "1205", "usb-0000:04:00.3-3/input0"),
                                ("hidraw2", "1205", "usb-0000:04:00.3-3/input2"),
                                ("hidraw3", "abcd", "usb-x/input2")):
        (dev / name).write_text("")
        device = sysfs / name / "device"
        device.mkdir(parents=True)
        vendor = "000028DE" if product != "abcd" else "0000045E"
        (device / "uevent").write_text(f"HID_ID=0003:{vendor}:0000{product}\nHID_PHYS={phys}\n")
    found = list(find_controllers(os.path.join(dev, "hidraw*"), str(sysfs)))
    assert found == [str(dev / "hidraw2")]


def test_combo_edges():
    combo = ComboDetector(["L4", "R4"])
    assert combo.update(frozenset({"L4"})) is None
    assert combo.update(frozenset({"L4", "R4"})) == "press"
    assert combo.update(frozenset({"L4", "R4", "A"})) is None
    assert combo.update(frozenset({"R4"})) == "release"
    assert combo.update(frozenset()) is None


def test_combo_reset_releases_a_held_binding():
    combo = ComboDetector(["R4"])
    combo.update(frozenset({"R4"}))
    assert combo.reset() == "release"
    assert combo.reset() is None


def test_normalize_binding():
    assert normalize_binding(["R4", "L4", "R4"]) == ["L4", "R4"]
    with pytest.raises(ValueError):
        normalize_binding([])
    with pytest.raises(ValueError):
        normalize_binding(["Steam"])
    with pytest.raises(ValueError):
        normalize_binding(["A", "B", "X", "Y", "L1"])


def run_capture(steps, deadline=100.0):
    capture = BindingCapture(deadline)
    for now, buttons in steps:
        capture.update(frozenset(buttons), now)
    return capture


def test_capture_waits_for_release_then_records_the_full_chord():
    capture = run_capture([
        (0.0, {"A"}),          # the A press that opened capture
        (0.1, set()),
        (0.4, set()),          # quiet for 250 ms -> listening
        (0.5, {"L4"}),
        (0.6, {"L4", "R4"}),
        (0.7, {"R4"}),         # staggered release keeps the chord
        (0.8, set()),
    ])
    assert capture.phase == "captured"
    assert capture.buttons == ["L4", "R4"]


def test_capture_ignores_the_opening_press():
    capture = run_capture([(0.0, {"A"}), (0.1, {"A"}), (0.2, set())])
    assert capture.phase == "release"


def test_capture_times_out():
    capture = run_capture([(0.0, set()), (0.3, set()), (11.0, {"L5"})], deadline=10.0)
    assert capture.phase == "cancelled"
    assert "unchanged" in capture.error


def test_capture_rejects_too_many_buttons():
    capture = run_capture([(0.0, set()), (0.3, set()), (0.4, {"A", "B", "L4", "R4", "L5"})])
    assert capture.phase == "cancelled"

"""Who the desktop user is, and which display Hex should talk to.

Decky runs plugin backends as root (HexDeck needs ``root`` to read the
controller's raw HID reports and to create its virtual keyboard). Hex itself
must run as the logged-in user: it keeps its settings, models and local API
discovery file in that user's home, and reaches the microphone through the
user's PipeWire session. This module finds that account and builds the
environment for every process HexDeck starts on the user's behalf.
"""

from __future__ import annotations

import glob
import os
import pwd
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class Account:
    name: str
    uid: int
    gid: int
    home: str

    @property
    def runtime_dir(self) -> str:
        return f"/run/user/{self.uid}"


def _from_pwd(entry) -> Account:
    return Account(entry.pw_name, entry.pw_uid, entry.pw_gid, entry.pw_dir)


def find_account(environ: Optional[dict] = None) -> Account:
    """The desktop account, without assuming it is called ``deck``.

    Decky exports ``DECKY_USER`` and ``DECKY_USER_HOME``; outside Decky (or
    when running unprivileged) the current user is the answer.
    """
    env = os.environ if environ is None else environ
    if os.geteuid() != 0:
        return _from_pwd(pwd.getpwuid(os.geteuid()))
    name = env.get("DECKY_USER")
    if name:
        try:
            return _from_pwd(pwd.getpwnam(name))
        except KeyError:
            pass
    home = env.get("DECKY_USER_HOME")
    if home:
        try:
            uid = os.stat(home).st_uid
            if uid != 0:
                return _from_pwd(pwd.getpwuid(uid))
        except (OSError, KeyError):
            pass
    try:
        return _from_pwd(pwd.getpwnam("deck"))
    except KeyError:
        pass
    raise RuntimeError("Cannot identify the desktop user to run Hex as")


def process_identity(account: Account) -> dict:
    """``subprocess`` keyword arguments that drop root to ``account``."""
    if os.geteuid() != 0:
        return {}
    return {"user": account.uid, "group": account.gid, "extra_groups": []}


def user_environment(account: Account, display: Optional[str] = None) -> dict:
    """A clean environment for a process run as the desktop user.

    The root environment Decky gives us is not copied: it names root's home
    and runtime directory, and Hex would look for its data in the wrong place.
    """
    path = ":".join([
        os.path.join(account.home, ".local", "bin"),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ])
    env = {
        "HOME": account.home,
        "USER": account.name,
        "LOGNAME": account.name,
        "PATH": path,
        "XDG_RUNTIME_DIR": account.runtime_dir,
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={account.runtime_dir}/bus",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    if display:
        env["DISPLAY"] = display
        # Hex adopts a Wayland socket when it sees a Wayland session behind
        # Xwayland. Gamescope's Wayland socket has no virtual keyboard or
        # data-control protocol, so pin Hex to X11, where its paste (XTest
        # plus the X11 clipboard) reaches games running under Xwayland.
        env["XDG_SESSION_TYPE"] = "x11"
    return env


# --- Display discovery -------------------------------------------------------

XpropRunner = Callable[[str], Optional[str]]


def x_displays(socket_dir: str = "/tmp/.X11-unix") -> list[str]:
    """X displays with a local socket, lowest number first."""
    names = []
    for path in glob.glob(os.path.join(socket_dir, "X[0-9]*")):
        suffix = os.path.basename(path)[1:]
        if suffix.isdigit():
            names.append(int(suffix))
    return [f":{number}" for number in sorted(names)]


def gamescope_running(account: Account) -> bool:
    return bool(glob.glob(os.path.join(account.runtime_dir, "gamescope-*")))


def xprop_runner(account: Account) -> XpropRunner:
    """Read ``GAMESCOPE_XWAYLAND_SERVER_ID`` from a display's root window."""

    def run(display: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["xprop", "-root", "GAMESCOPE_XWAYLAND_SERVER_ID"],
                env=user_environment(account, display),
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
                **process_identity(account),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout if result.returncode == 0 else None

    return run


def parse_server_id(xprop_output: Optional[str]) -> Optional[int]:
    """``GAMESCOPE_XWAYLAND_SERVER_ID(CARDINAL) = 0`` -> 0."""
    if not xprop_output or "=" not in xprop_output:
        return None
    value = xprop_output.rsplit("=", 1)[1].strip()
    return int(value) if value.isdigit() else None


@dataclass(frozen=True)
class DisplayChoice:
    display: Optional[str]
    # "gamescope": Game Mode, Hex should run under HexDeck.
    # "desktop": a desktop session (or nothing at all); HexDeck leaves the
    # user's own Hex alone.
    kind: str
    reason: str


def choose_display(
    override: str,
    candidates: list[str],
    gamescope: bool,
    server_id: XpropRunner,
) -> DisplayChoice:
    """Pick the Xwayland display games are on.

    Gamescope publishes ``GAMESCOPE_XWAYLAND_SERVER_ID`` on each of its
    Xwayland servers; server 0 is the one Steam starts games on. When
    ``xprop`` is unavailable, fall back to ``:1`` (where SteamOS has run
    games for years), then the first display.
    """
    if override and override != "auto":
        return DisplayChoice(override, "gamescope" if gamescope else "desktop", "set in HexDeck")
    if not gamescope:
        return DisplayChoice(candidates[0] if candidates else None, "desktop", "Gamescope isn't running")
    for display in candidates:
        if parse_server_id(server_id(display)) == 0:
            return DisplayChoice(display, "gamescope", "Gamescope's main Xwayland")
    if ":1" in candidates:
        return DisplayChoice(":1", "gamescope", "Gamescope (assumed :1)")
    if candidates:
        return DisplayChoice(candidates[0], "gamescope", "Gamescope (first display)")
    return DisplayChoice(None, "gamescope", "Gamescope has no Xwayland display yet")


def detect_display(account: Account, override: str = "auto") -> DisplayChoice:
    return choose_display(
        override,
        x_displays(),
        gamescope_running(account),
        xprop_runner(account),
    )

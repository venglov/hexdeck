"""Hex's control CLI, run as the desktop user.

Every Hex control command takes ``--json`` and answers a versioned
``ControlResponse`` on stdout with a stable exit code (Hex's docs/cli.md):

    0 done, or nothing to change       1 refused or failed
    2 usage error                      3 Hex isn't running
    4 no speech (``--print`` commands)

HexDeck never talks to Hex's local API directly; the CLI is Hex's supported
contract and keeps working across Hex's wire-format versions.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from .session import Account, process_identity, user_environment

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_NOT_RUNNING = 3
EXIT_NO_SPEECH = 4


@dataclass
class HexResult:
    code: int
    reply: dict = field(default_factory=dict)
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.code == EXIT_OK

    @property
    def message(self) -> str:
        """The most useful human-readable explanation of the reply."""
        text = self.reply.get("message") if isinstance(self.reply, dict) else None
        if text:
            return str(text)
        if self.code == EXIT_NOT_RUNNING:
            return "Hex isn't running"
        if self.code == EXIT_NO_SPEECH:
            return "No speech heard"
        return self.stderr.strip().splitlines()[-1] if self.stderr.strip() else f"hex exited {self.code}"


def parse_reply(stdout: str) -> dict:
    """The JSON reply, tolerating log lines before it."""
    stdout = stdout.strip()
    if not stdout:
        return {}
    try:
        value = json.loads(stdout)
        return value if isinstance(value, dict) else {"value": value}
    except ValueError:
        pass
    # Take the last line that parses as an object.
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    return value
            except ValueError:
                continue
    return {"message": stdout.splitlines()[-1]}


def candidate_paths(account: Account, configured: str = "") -> list[str]:
    paths = []
    if configured:
        paths.append(os.path.expanduser(configured))
    paths += [
        os.path.join(account.home, ".local", "bin", "hex"),
        "/usr/bin/hex",
        "/usr/local/bin/hex",
    ]
    which = shutil.which("hex", path=user_environment(account)["PATH"])
    if which:
        paths.append(which)
    return list(dict.fromkeys(paths))


def find_hex(account: Account, configured: str = "") -> Optional[str]:
    for path in candidate_paths(account, configured):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


class HexCli:
    """Runs ``hex <args> --json`` as the desktop user."""

    def __init__(self, account: Account, binary: str, display: Optional[str] = None):
        self.account = account
        self.binary = binary
        self.display = display

    def environment(self) -> dict:
        return user_environment(self.account, self.display)

    def run(self, *args: str, timeout: float = 20.0, json_flag: bool = True) -> HexResult:
        argv = [self.binary, *args]
        if json_flag:
            argv.append("--json")
        try:
            completed = subprocess.run(
                argv,
                env=self.environment(),
                cwd=self.account.home,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                **process_identity(self.account),
            )
        except subprocess.TimeoutExpired:
            return HexResult(EXIT_FAILED, {"message": f"hex {args[0] if args else ''} timed out"})
        except OSError as error:
            return HexResult(EXIT_FAILED, {"message": f"Could not run Hex: {error.strerror or error}"})
        return HexResult(completed.returncode, parse_reply(completed.stdout), completed.stderr)

    # -- Convenience wrappers ------------------------------------------------

    def version(self) -> Optional[str]:
        result = self.run("--version", timeout=5, json_flag=False)
        if not result.ok:
            return None
        text = result.reply.get("message", "")
        return text.split()[-1] if text else None

    def status(self) -> HexResult:
        return self.run("status", timeout=5)

    def dictation(self, action: str, print_text: bool = False) -> HexResult:
        args = ["dictation", action]
        if print_text:
            args.append("--print")
        # ``stop --print`` waits up to 60 s for the transcript; Hex's own CLI
        # waits 70 s.
        return self.run(*args, timeout=75 if print_text else 20)

    def models(self) -> HexResult:
        return self.run("model", "list", timeout=20)

    def use_model(self, model_id: str, language: str = "") -> HexResult:
        args = ["model", "use", model_id]
        if language:
            args += ["--language", language]
        return self.run(*args, timeout=30)

    def install_model(self, model_id: str, language: str = "") -> HexResult:
        args = ["model", "install", model_id]
        if language:
            args += ["--language", language]
        return self.run(*args, timeout=30)

    def cancel_model(self) -> HexResult:
        return self.run("model", "cancel", timeout=10)

    def get_setting(self, key: str) -> HexResult:
        return self.run("settings", "get", key, timeout=10)

    def set_setting(self, key: str, value: str) -> HexResult:
        return self.run("settings", "set", key, value, timeout=10)

    def quit(self, force: bool = False) -> HexResult:
        args = ["quit"] + (["--force"] if force else [])
        return self.run(*args, timeout=20)


def setting_value(reply: dict, key: str):
    """A setting's value from a ``settings`` reply, or ``None``."""
    for entry in reply.get("settings", []) or []:
        if isinstance(entry, dict) and entry.get("key") == key:
            return entry.get("value")
    return None

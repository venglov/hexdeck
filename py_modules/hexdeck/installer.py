"""Install the official Hex Linux build into ``~/.local/bin/hex``.

This follows Hex's own installer (``.github/release/install-linux.sh`` in the
Hex repository) step for step, so the result is the same file the official
script installs, checked the same way:

1. fetch the channel manifest (``stable``, else ``dev`` while there is no
   stable release) from ``https://anoma.ly/release/hex/desktop/``;
2. check its schema, the target's size limit and file URL shape;
3. download the executable and check its size and SHA-256;
4. download its 64-byte signature and verify it with Hex's Ed25519 release
   key over ``anomaly.hex.linux-artifact.v1\\n<sha256>\\n``;
5. move it into place, owned by the desktop user.

Unlike the official script it doesn't install a desktop entry, autostart
entry, or systemd unit: in Game Mode HexDeck runs Hex itself. Installing Hex
in Desktop Mode with the official script afterwards is fine; it replaces the
same file.

Downloads use ``curl`` as the desktop user, as Hex's script does, so they
use SteamOS's own CA store and never write as root.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from . import ed25519
from .session import Account, process_identity, user_environment

ORIGIN = "https://anoma.ly/release"
HOST = "https://anoma.ly"
SIGNING_KEY = "MCowBQYDK2VwAyEAv60C5iII/xRLXJ0hx+ecfBbGkEKZpDfYVzAwB81P99g="
SIGNED_PREFIX = b"anomaly.hex.linux-artifact.v1\n"
MAX_ARTIFACT_BYTES = 536870912
FILE_URL = re.compile(r"^/([A-Za-z0-9._-]+/)*hex/files/[0-9a-f]{64}/[A-Za-z0-9._-]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class InstallError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    channel: str
    version: str
    url: str
    size: int
    sha256: str
    signature_url: str
    signature_sha256: str


def target_name(machine: Optional[str] = None) -> str:
    machine = machine or platform.machine()
    if machine in ("x86_64", "amd64"):
        return "linux-x64"
    if machine in ("aarch64", "arm64"):
        return "linux-arm64"
    raise InstallError(f"Hex has no Linux build for {machine}")


def parse_manifest(text: str, channel: str, target: str) -> Release:
    try:
        manifest = json.loads(text)
    except ValueError as error:
        raise InstallError("The Hex release manifest isn't JSON") from error
    identity = (manifest.get("schema"), manifest.get("app"), manifest.get("artifact"), manifest.get("channel"))
    if identity != (1, "hex", "desktop", channel):
        raise InstallError(f"That isn't the Hex desktop {channel} manifest")
    release = manifest.get("release") or {}
    targets = release.get("targets") or {}
    build = targets.get(target)
    signature = targets.get(f"{target}-sig")
    version = release.get("version")
    if not isinstance(version, str) or not version:
        raise InstallError("The manifest names no version")
    if not isinstance(build, dict):
        raise InstallError(f"Hex {version} has no {target} build")
    if not isinstance(signature, dict):
        raise InstallError(f"Hex {version} has no signature for {target}")
    size = build.get("size")
    if not isinstance(size, int) or size <= 0 or size > MAX_ARTIFACT_BYTES:
        raise InstallError("The Linux release has an invalid size")
    for entry in (build, signature):
        if not isinstance(entry.get("sha256"), str) or not SHA256.match(entry["sha256"]):
            raise InstallError("The Linux release has an invalid checksum")
        if not isinstance(entry.get("url"), str) or not FILE_URL.match(entry["url"]):
            raise InstallError("The Linux release names an unexpected file URL")
    if signature.get("size") != 64:
        raise InstallError("The Linux release has an invalid signature")
    return Release(channel, version, build["url"], size, build["sha256"],
                   signature["url"], signature["sha256"])


def verify_signature(sha256: str, signature: bytes, key: str = SIGNING_KEY) -> bool:
    public_key = ed25519.public_key_from_spki(base64.b64decode(key))
    return ed25519.verify(public_key, SIGNED_PREFIX + sha256.encode() + b"\n", signature)


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Installer:
    """One install at a time, in a background thread, with progress."""

    def __init__(self, account: Account, on_change: Callable[[], None] = lambda: None):
        self.account = account
        self.on_change = on_change
        self.thread: Optional[threading.Thread] = None
        self.state = "idle"  # idle | running | done | failed
        self.stage = ""
        self.error = ""
        self.version = ""
        self.received = 0
        self.total = 0
        self._partial: Optional[str] = None

    @property
    def destination(self) -> str:
        return os.path.join(self.account.home, ".local", "bin", "hex")

    def snapshot(self) -> dict:
        received = self.received
        if self._partial and os.path.exists(self._partial):
            try:
                received = os.path.getsize(self._partial)
            except OSError:
                pass
        return {"state": self.state, "stage": self.stage, "error": self.error,
                "version": self.version, "received": received, "total": self.total}

    def start(self, channel: str = "") -> bool:
        if self.thread and self.thread.is_alive():
            return False
        self.state, self.stage, self.error = "running", "Checking the latest release", ""
        self.received = self.total = 0
        self.thread = threading.Thread(target=self._run, args=(channel,), name="hexdeck-install", daemon=True)
        self.thread.start()
        return True

    # -- Steps ---------------------------------------------------------------

    def _curl(self, url: str, path: str, limit: int, seconds: int) -> int:
        """Download ``url`` to ``path``; return the HTTP status."""
        argv = ["curl", "--location", "--proto", "=https", "--proto-redir", "=https",
                "--silent", "--show-error", "--connect-timeout", "10",
                "--max-time", str(seconds), "--max-filesize", str(limit),
                "--output", path, "--write-out", "%{http_code}", url]
        try:
            result = subprocess.run(argv, env=user_environment(self.account), capture_output=True,
                                    text=True, timeout=seconds + 15, check=False,
                                    **process_identity(self.account))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise InstallError(f"Could not download {url}: {error}") from error
        status = int(result.stdout.strip() or 0) if result.stdout.strip().isdigit() else 0
        if result.returncode != 0 and status == 0:
            raise InstallError(f"Could not reach {url}: {result.stderr.strip() or 'curl failed'}")
        return status

    def _manifest(self, folder: str, channel: str, target: str) -> Release:
        path = os.path.join(folder, "manifest.json")
        channels = [channel] if channel else ["stable", "dev"]
        for name in channels:
            status = self._curl(f"{ORIGIN}/hex/desktop/{name}.json", path, 1048576, 60)
            if status == 200:
                with open(path) as stream:
                    return parse_manifest(stream.read(), name, target)
            if status == 404 and name == "stable" and not channel:
                continue  # No stable release yet: Hex's script installs dev.
            raise InstallError(f"The Hex {name} manifest answered HTTP {status}")
        raise InstallError("Hex has no release to install")

    def _run(self, channel: str) -> None:
        folder = None
        try:
            if shutil.which("curl", path=user_environment(self.account)["PATH"]) is None:
                raise InstallError("Installing Hex needs curl")
            target = target_name()
            bin_dir = os.path.dirname(self.destination)
            self._make_user_dir(bin_dir)
            # A temporary folder next to the destination, owned by the user,
            # so curl (running as that user) can write into it and the final
            # rename stays on one filesystem.
            folder = tempfile.mkdtemp(prefix=".hexdeck-install-", dir=bin_dir)
            self._chown(folder)
            release = self._manifest(folder, channel, target)
            self.version, self.total = release.version, release.size
            self.stage = f"Downloading Hex {release.version}"
            self.on_change()

            artifact = os.path.join(folder, "hex")
            self._partial = artifact
            status = self._curl(HOST + release.url, artifact, release.size, 900)
            self._partial = None
            if status != 200:
                raise InstallError(f"Downloading Hex answered HTTP {status}")
            if os.path.getsize(artifact) != release.size:
                raise InstallError("The download has the wrong size")
            self.received = release.size
            self.stage = "Verifying the download"
            self.on_change()
            if file_sha256(artifact) != release.sha256:
                raise InstallError("The download's checksum doesn't match")

            signature_path = os.path.join(folder, "hex.sig")
            status = self._curl(HOST + release.signature_url, signature_path, 64, 60)
            if status != 200:
                raise InstallError(f"Downloading the signature answered HTTP {status}")
            if file_sha256(signature_path) != release.signature_sha256:
                raise InstallError("The signature's checksum doesn't match")
            with open(signature_path, "rb") as stream:
                signature = stream.read()
            if not verify_signature(release.sha256, signature):
                raise InstallError("The release signature doesn't verify; refusing to install it")

            os.chmod(artifact, 0o755)
            self._chown(artifact)
            os.replace(artifact, self.destination)
            self.state, self.stage = "done", f"Installed Hex {release.version}"
        except InstallError as error:
            self.state, self.error = "failed", str(error)
        except Exception as error:  # pragma: no cover - unexpected
            self.state, self.error = "failed", f"Install failed: {error}"
        finally:
            self._partial = None
            if folder:
                shutil.rmtree(folder, ignore_errors=True)
            self.on_change()

    def _make_user_dir(self, path: str) -> None:
        missing = []
        current = path
        while not os.path.isdir(current):
            missing.append(current)
            current = os.path.dirname(current)
        for directory in reversed(missing):
            os.mkdir(directory, 0o755)
            self._chown(directory)
        if os.path.islink(path):
            raise InstallError(f"Refusing to install into a symlinked folder: {path}")

    def _chown(self, path: str) -> None:
        if os.geteuid() == 0:
            os.chown(path, self.account.uid, self.account.gid)

"""Run and supervise ``hex service`` for Game Mode.

``hex service`` is Hex's own headless entry point (the one its systemd unit
runs): the listener, model downloads, sounds and paste, without a window.
HexDeck starts it as the desktop user on Gamescope's Xwayland display, and
restarts it if it crashes.

Hex is one process per user. When a Hex already answers (the user's desktop
Hex, or one left from an earlier plugin load), HexDeck uses it instead of
starting a second one, and says so.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from typing import Callable, Optional

from .hexcli import EXIT_OK, HexCli
from .session import Account, process_identity

logger = logging.getLogger("hexdeck.service")

READY_TIMEOUT = 20.0
RESTART_WINDOW = 120.0
MAX_RESTARTS = 5


class RestartBudget:
    """At most ``limit`` restarts within ``window`` seconds."""

    def __init__(self, limit: int = MAX_RESTARTS, window: float = RESTART_WINDOW,
                 clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.starts: list[float] = []

    def allow(self) -> bool:
        now = self.clock()
        self.starts = [start for start in self.starts if now - start < self.window]
        if len(self.starts) >= self.limit:
            return False
        self.starts.append(now)
        return True

    def reset(self) -> None:
        self.starts.clear()


class HexService:
    def __init__(self, account: Account, log_path: str):
        self.account = account
        self.log_path = log_path
        self.process: Optional[subprocess.Popen] = None
        self.cli: Optional[HexCli] = None
        self.external = False
        self.error = ""
        self.lock = threading.RLock()
        self.budget = RestartBudget()
        self.wanted = False

    # -- State ---------------------------------------------------------------

    @property
    def owned_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def display(self) -> Optional[str]:
        return self.cli.display if self.cli else None

    def answers(self) -> bool:
        return self.cli is not None and self.cli.status().code == EXIT_OK

    # -- Lifecycle -----------------------------------------------------------

    def start(self, cli: HexCli) -> bool:
        """Make sure a Hex answers on ``cli``'s display; start one if needed."""
        with self.lock:
            self.wanted = True
            if self.owned_running and self.cli and self.cli.display == cli.display \
                    and self.cli.binary == cli.binary:
                return True
            if self.owned_running:
                self._stop_owned()
            self.cli = cli
            if cli.status().code == EXIT_OK:
                # Someone else's Hex (or one we started before a reload).
                self.external = True
                self.error = ""
                logger.info("Using the Hex that is already running")
                return True
            self.external = False
            return self._spawn()

    def _spawn(self) -> bool:
        assert self.cli is not None
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        log = open(self.log_path, "ab", buffering=0)
        try:
            log.write(f"\n--- hex service on {self.cli.display} at {time.ctime()} ---\n".encode())
            self.process = subprocess.Popen(
                [self.cli.binary, "service"],
                env=self.cli.environment(),
                cwd=self.account.home,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                **process_identity(self.account),
            )
        except OSError as error:
            self.error = f"Could not start Hex: {error.strerror or error}"
            logger.error(self.error)
            return False
        finally:
            log.close()
        deadline = time.monotonic() + READY_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                # Lost the one-Hex-per-user race: another Hex answers.
                if self.cli.status().code == EXIT_OK:
                    self.process = None
                    self.external = True
                    self.error = ""
                    return True
                self.error = f"Hex exited during startup (code {self.process.returncode}); see {self.log_path}"
                logger.error(self.error)
                self.process = None
                return False
            if self.cli.status().code == EXIT_OK:
                self.error = ""
                logger.info("Hex service is ready on %s (pid %s)", self.cli.display, self.process.pid)
                return True
            time.sleep(0.5)
        self.error = "Hex didn't answer within 20 seconds"
        logger.error(self.error)
        return False

    def supervise(self) -> None:
        """Called periodically: restart our Hex if it died."""
        with self.lock:
            if not self.wanted or self.cli is None or self.external:
                return
            if self.owned_running:
                return
            if self.process is not None:
                code = self.process.returncode
                logger.warning("Hex service exited with code %s", code)
                self.process = None
            if not self.budget.allow():
                self.error = f"Hex keeps exiting; stopped restarting it. See {self.log_path}"
                return
            self._spawn()

    def stop(self) -> None:
        with self.lock:
            self.wanted = False
            if self.owned_running:
                self._stop_owned()
            self.external = False

    def _stop_owned(self) -> None:
        assert self.process is not None
        if self.cli is not None:
            self.cli.quit(force=True)
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    def take_over(self, cli: HexCli) -> bool:
        """Quit an external Hex and start one under HexDeck on ``cli``'s display."""
        with self.lock:
            if self.external and self.cli is not None:
                self.cli.quit(force=True)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and self.cli.status().code == EXIT_OK:
                    time.sleep(0.5)
            self.external = False
            self.budget.reset()
            self.cli = None
            return self.start(cli)

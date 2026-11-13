"""Deleting a downloaded Hex model on Linux.

Hex's CLI has no delete for catalog models on Linux: ``hex model remove``
covers Labs imports only, and Hex's Linux Settings don't offer deletion yet
(Hex's docs/features/README.md, "Delete downloaded models"). The macOS
picker's delete is ``transcription::models::remove_installed_at``; this is
the same steps, on the path ``hex model status <id>`` reports:

1. take the models folder's ``.download.lock`` (fs2 ``flock``) without
   waiting, so a download in progress is never touched;
2. delete the model, its verification receipt and any partial download;
3. sync the folder.

The backend runs as root, so it never creates a file in the user's folder
(a root-owned lock file would break Hex's next download). With no lock file,
nothing has ever downloaded there, so there is nothing to wait for.
"""

from __future__ import annotations

import errno
import fcntl
import os

LOCK_NAME = ".download.lock"


class RemoveError(Exception):
    pass


def companion_files(path: str) -> list:
    """The model and the files Hex keeps beside it (``with_extension``)."""
    return [path, path + ".verified.json", path + ".partial"]


def _inside(path: str, folder: str) -> bool:
    folder = os.path.realpath(folder)
    return os.path.commonpath([os.path.realpath(path), folder]) == folder


def remove_model_files(path: str, home: str) -> None:
    """Delete the model at ``path`` (from ``hex model status``) and its
    companions. Refuses a path outside ``home`` or one that isn't a GGUF."""
    if not path or not os.path.isabs(path) or not path.endswith(".gguf"):
        raise RemoveError(f"Hex reported an unexpected model path: {path or 'none'}")
    directory = os.path.dirname(path)
    if not _inside(directory, home):
        raise RemoveError(f"{path} isn't in your home folder; HexDeck leaves it alone")
    if not os.path.isdir(directory):
        return
    lock_path = os.path.join(directory, LOCK_NAME)
    lock = None
    try:
        try:
            lock = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            lock = None
        except OSError as error:
            raise RemoveError(f"Couldn't open {lock_path}: {error.strerror}") from error
        if lock is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise RemoveError("A model download is in progress. Try again when it finishes.") from error
                raise RemoveError(f"Couldn't lock {lock_path}: {error.strerror}") from error
        for file in companion_files(path):
            try:
                os.remove(file)
            except FileNotFoundError:
                pass
            except OSError as error:
                raise RemoveError(f"Couldn't delete {file}: {error.strerror}") from error
        folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        if lock is not None:
            os.close(lock)

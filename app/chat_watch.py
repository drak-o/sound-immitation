"""Follow Minecraft's latest.log and yield chat text."""

from __future__ import annotations

import re
import time
from pathlib import Path

from app.deaths import DeathMatcher

_CHAT_MARK = "[CHAT] "
_NOT_SECURE = "[Not Secure] "
_COLOR = re.compile(r"§.")


def extract_chat(line: str) -> str | None:
    index = line.rfind(_CHAT_MARK)
    if index < 0:
        return None
    text = line[index + len(_CHAT_MARK) :].strip()
    if text.startswith(_NOT_SECURE):
        text = text[len(_NOT_SECURE) :].strip()
    text = _COLOR.sub("", text).replace("§", "").strip()
    if not text:
        return None
    return text


class ChatWatch:
    """Tail a log that Minecraft replaces on launch.

    The file is not held open. On Windows a standing read handle blocks the
    game from renaming latest.log, so each poll opens, reads, and closes.
    """

    def __init__(self, log_path: Path) -> None:
        self._path = Path(log_path)
        self._offset = 0
        self._identity: tuple[int, int, int] | None = None
        self._pending = b""
        self._announced_wait = False
        self._seek_end()

    def next_chat(self) -> str:
        while True:
            text = self._poll_chat()
            if text is not None:
                return text
            time.sleep(0.1)

    def wait_for_death(self, matcher: DeathMatcher) -> str:
        while True:
            text = self.next_chat()
            if matcher.matches(text):
                return text

    def drain(self) -> None:
        self._seek_end()

    def _poll_chat(self) -> str | None:
        while True:
            line = self._read_line()
            if line is None:
                return None
            text = extract_chat(line)
            if text is not None:
                return text

    def _read_line(self) -> str | None:
        if not self._path.is_file():
            self._offset = 0
            self._identity = None
            self._pending = b""
            return None
        stat = self._path.stat()
        identity = (stat.st_dev, stat.st_ino, stat.st_ctime_ns)
        if identity != self._identity or stat.st_size < self._offset:
            self._identity = identity
            self._offset = 0
            self._pending = b""
        if stat.st_size > self._offset:
            with self._path.open("rb") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
            self._offset += len(chunk)
            self._pending += chunk
        return self._pop_line()

    def _pop_line(self) -> str | None:
        if b"\n" not in self._pending:
            return None
        raw, self._pending = self._pending.split(b"\n", 1)
        return raw.decode("utf-8", errors="replace").rstrip("\r")

    def _seek_end(self) -> None:
        while not self._path.is_file():
            if not self._announced_wait:
                print(f"Waiting for {self._path}")
                self._announced_wait = True
            time.sleep(0.2)
        stat = self._path.stat()
        self._identity = (stat.st_dev, stat.st_ino, stat.st_ctime_ns)
        self._offset = stat.st_size
        self._pending = b""

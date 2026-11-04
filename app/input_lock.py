"""Swallow keyboard and mouse input until the panic shortcut."""

from __future__ import annotations

import atexit
import threading

from pynput import keyboard, mouse


class InputLock:
    def __init__(self) -> None:
        self.panicked = threading.Event()
        self._keyboard: keyboard.Listener | None = None
        self._mouse: mouse.Listener | None = None
        atexit.register(self.stop)

    def start(self, panic_shortcut: str) -> None:
        if self._keyboard is not None:
            self.stop()
        # A panic from the previous lock must not abort this one.
        self.panicked.clear()
        try:
            self._keyboard = keyboard.GlobalHotKeys(
                {panic_shortcut: self.panicked.set}, suppress=True
            )
        except ValueError:
            raise SystemExit(f"Invalid panic_shortcut: {panic_shortcut}") from None
        self._mouse = mouse.Listener(suppress=True)
        self._keyboard.start()
        self._mouse.start()
        self._keyboard.wait()
        self._mouse.wait()

    def stop(self) -> None:
        listeners = (self._keyboard, self._mouse)
        self._keyboard = None
        self._mouse = None
        for listener in listeners:
            if listener is not None:
                listener.stop()
        for listener in listeners:
            if listener is not None:
                listener.join(timeout=2)

"""Swallow keyboard and mouse input until the panic shortcut."""

from __future__ import annotations

import atexit

from pynput import keyboard, mouse
from pynput.keyboard import Key


def _parse_shortcut(shortcut: str) -> tuple[str, ...]:
    parts = [part.strip().lower() for part in shortcut.split("+") if part.strip()]
    if not parts:
        raise SystemExit("panic_shortcut is empty.")
    for name in parts:
        # A letter has no Key attribute. The hook reports it as a character.
        if len(name) == 1 and name.isalpha():
            continue
        try:
            getattr(Key, name)
        except AttributeError:
            raise SystemExit(f"Unknown key in panic_shortcut: {name}") from None
    return tuple(parts)


def _held_name(key):
    if isinstance(key, Key):
        return key.name
    char = getattr(key, "char", None)
    if isinstance(char, str) and len(char) == 1 and char.isalpha():
        return char.lower()
    return key


class InputLock:
    def __init__(self) -> None:
        self._keyboard: keyboard.Listener | None = None
        self._mouse: mouse.Listener | None = None
        self._keys: tuple[str, ...] = ()
        self._held: set = set()
        self._on_panic = None
        atexit.register(self.stop)

    def start(self, panic_shortcut: str, on_panic) -> None:
        if self._keyboard is not None:
            self.stop()
        self._keys = _parse_shortcut(panic_shortcut)
        self._held.clear()
        self._on_panic = on_panic
        self._keyboard = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release, suppress=True
        )
        self._mouse = mouse.Listener(suppress=True)
        self._keyboard.start()
        self._mouse.start()
        self._keyboard.wait()
        self._mouse.wait()

    def stop(self) -> None:
        listeners = (self._keyboard, self._mouse)
        self._keyboard = None
        self._mouse = None
        self._on_panic = None
        for listener in listeners:
            if listener is not None:
                listener.stop()
        for listener in listeners:
            if listener is not None:
                listener.join(timeout=2)

    def _on_press(self, key) -> None:
        name = _held_name(key)
        if name is None:
            return
        self._held.add(name)
        # The hook reports ctrl_l or ctrl_r. The name ctrl matches either.
        if all(
            part in self._held or f"{part}_l" in self._held or f"{part}_r" in self._held
            for part in self._keys
        ):
            callback = self._on_panic
            if callback is not None:
                callback()

    def _on_release(self, key) -> None:
        self._held.discard(_held_name(key))

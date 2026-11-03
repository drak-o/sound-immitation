"""Swallow keyboard and mouse input until the panic shortcut."""

from __future__ import annotations

import atexit

from pynput import keyboard, mouse
from pynput.keyboard import Key

# A low-level hook reports the left or right key, not the generic Ctrl/Alt/Shift code.
_MODIFIERS = {
    "ctrl": frozenset({Key.ctrl, Key.ctrl_l, Key.ctrl_r}),
    "control": frozenset({Key.ctrl, Key.ctrl_l, Key.ctrl_r}),
    "alt": frozenset({Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr}),
    "shift": frozenset({Key.shift, Key.shift_l, Key.shift_r}),
}

_NAMED_KEYS = {
    "esc": Key.esc,
    "escape": Key.esc,
    "pause": Key.pause,
    "end": Key.end,
    "space": Key.space,
    "tab": Key.tab,
    "backspace": Key.backspace,
}


def _shortcut_key(name: str):
    if len(name) == 1 and name.isalpha():
        return name.lower()
    if name.startswith("f") and name[1:].isdigit():
        number = int(name[1:])
        if 1 <= number <= 12:
            return getattr(Key, name)
    if name in _NAMED_KEYS:
        return _NAMED_KEYS[name]
    raise SystemExit(f"Unknown key in panic_shortcut: {name}")


def _parse_shortcut(shortcut: str) -> tuple[tuple[frozenset, ...], object]:
    parts = [part.strip().lower() for part in shortcut.split("+") if part.strip()]
    if not parts:
        raise SystemExit("panic_shortcut is empty.")
    try:
        modifiers = tuple(_MODIFIERS[part] for part in parts[:-1])
    except KeyError as error:
        raise SystemExit(
            f"Unknown modifier in panic_shortcut: {error.args[0]}"
        ) from error
    return modifiers, _shortcut_key(parts[-1])


def _held_name(key):
    if isinstance(key, Key):
        return key
    char = getattr(key, "char", None)
    if isinstance(char, str) and len(char) == 1 and char.isalpha():
        return char.lower()
    return key


class InputLock:
    def __init__(self) -> None:
        self._keyboard: keyboard.Listener | None = None
        self._mouse: mouse.Listener | None = None
        self._modifiers: tuple[frozenset, ...] = ()
        self._key = None
        self._held: set = set()
        self._on_panic = None
        atexit.register(self.stop)

    def start(self, panic_shortcut: str, on_panic) -> None:
        if self._keyboard is not None:
            self.stop()
        self._modifiers, self._key = _parse_shortcut(panic_shortcut)
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
        if self._key in self._held and all(
            any(code in self._held for code in group) for group in self._modifiers
        ):
            callback = self._on_panic
            if callback is not None:
                callback()

    def _on_release(self, key) -> None:
        self._held.discard(_held_name(key))

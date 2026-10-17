"""Swallow keyboard and mouse input until the panic chord."""

from __future__ import annotations

import atexit
import ctypes
import threading
from ctypes import wintypes

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012

_MODIFIER_CODES = {
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
}

_NAMED_KEYS = {
    "esc": 0x1B,
    "escape": 0x1B,
    "pause": 0x13,
    "end": 0x23,
    "space": 0x20,
    "tab": 0x09,
    "backspace": 0x08,
}

# The hook runs on its own thread. Windows drops a hook that stalls past
# LowLevelHooksTimeout, so this procedure only reads key state and sets an event.
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def _key_code(name: str) -> int:
    if len(name) == 1 and name.isalpha():
        return ord(name.upper())
    if name.startswith("f") and name[1:].isdigit():
        number = int(name[1:])
        if 1 <= number <= 12:
            return 0x70 + number - 1
    if name in _NAMED_KEYS:
        return _NAMED_KEYS[name]
    raise SystemExit(f"Unknown key in panic_chord: {name}")


def _parse_chord(chord: str) -> tuple[tuple[int, ...], int]:
    parts = [part.strip().lower() for part in chord.split("+") if part.strip()]
    if not parts:
        raise SystemExit("panic_chord is empty.")
    try:
        modifiers = tuple(_MODIFIER_CODES[part] for part in parts[:-1])
    except KeyError as error:
        raise SystemExit(f"Unknown modifier in panic_chord: {error.args[0]}") from error
    return modifiers, _key_code(parts[-1])


class InputLock:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._keyboard_hook = None
        self._mouse_hook = None
        self._modifiers: tuple[int, ...] = ()
        self._key = 0
        self._on_panic = None
        self._error: OSError | None = None
        self._keyboard_hook_proc = HOOKPROC(self._keyboard_proc)
        self._mouse_hook_proc = HOOKPROC(self._mouse_proc)
        atexit.register(self.stop)

    def start(self, panic_chord: str, on_panic) -> None:
        if self._thread is not None:
            self.stop()
        self._modifiers, self._key = _parse_chord(panic_chord)
        self._on_panic = on_panic
        self._error = None
        ready = threading.Event()
        self._thread = threading.Thread(target=self._pump, args=(ready,), name="input-lock", daemon=True)
        self._thread.start()
        if not ready.wait(timeout=3):
            raise SystemExit("Input lock did not start.")
        if self._error is not None:
            self._thread.join(timeout=2)
            self._thread = None
            self._thread_id = None
            raise SystemExit(f"Input lock failed: {self._error}")

    def stop(self) -> None:
        thread = self._thread
        thread_id = self._thread_id
        if thread_id:
            user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        self._thread_id = None
        self._on_panic = None

    def _pump(self, ready: threading.Event) -> None:
        self._thread_id = int(kernel32.GetCurrentThreadId())
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self._keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._keyboard_hook_proc, None, 0)
        self._mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_hook_proc, None, 0)
        if not self._keyboard_hook or not self._mouse_hook:
            self._error = ctypes.WinError(ctypes.get_last_error())
            self._unhook()
            ready.set()
            return
        ready.set()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        self._unhook()

    def _unhook(self) -> None:
        if self._keyboard_hook:
            user32.UnhookWindowsHookEx(self._keyboard_hook)
            self._keyboard_hook = None
        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None

    def _keyboard_proc(self, n_code, w_param, l_param):
        if n_code < 0:
            return user32.CallNextHookEx(self._keyboard_hook, n_code, w_param, l_param)
        try:
            if self._is_panic():
                callback = self._on_panic
                if callback is not None:
                    callback()
                return user32.CallNextHookEx(self._keyboard_hook, n_code, w_param, l_param)
        except Exception:
            return 1
        return 1

    def _mouse_proc(self, n_code, w_param, l_param):
        if n_code < 0:
            return user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)
        return 1

    def _is_panic(self) -> bool:
        if not user32.GetAsyncKeyState(self._key) & 0x8000:
            return False
        return all(user32.GetAsyncKeyState(modifier) & 0x8000 for modifier in self._modifiers)

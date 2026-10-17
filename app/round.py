"""One imitation attempt, or a locked retry until the score passes."""

from __future__ import annotations

import threading
import time

from app.audio import AudioSession, Clip
from app.config import Config
from app.input_lock import InputLock
from app.overlay_server import OverlayHub
from app.score import Scorer

_RESULT_HOLD_SECONDS = 1.5
_COLUMNS = 400


class RoundController:
    def __init__(
        self,
        config: Config,
        audio: AudioSession,
        scorer: Scorer,
        hub: OverlayHub,
        lock: InputLock,
    ) -> None:
        self._config = config
        self._audio = audio
        self._scorer = scorer
        self._hub = hub
        self._lock = lock

    def run_demo(self) -> None:
        abort = threading.Event()
        try:
            clip = self._audio.pick_random(self._config.sounds_dir)
            percent = self._one_take(clip, 1, abort)
            print(f"passed={percent >= self._config.threshold_percent}")
            self._hold(abort)
        finally:
            self._hub.publish({"type": "idle"})

    def run_locked(self) -> None:
        abort = threading.Event()
        self._lock.start(self._config.panic_chord, abort.set)
        try:
            clip = self._audio.pick_random(self._config.sounds_dir)
            attempt = 1
            while not abort.is_set():
                percent = self._one_take(clip, attempt, abort)
                if abort.is_set():
                    break
                passed = percent >= self._config.threshold_percent
                print(f"attempt={attempt} passed={passed}")
                self._hold(abort)
                if passed:
                    break
                attempt += 1
        finally:
            self._lock.stop()
            self._hub.publish({"type": "idle"})

    def _one_take(self, clip: Clip, attempt: int, abort: threading.Event) -> float:
        self._hub.publish(
            {
                "type": "reference",
                "peaks": clip.peaks,
                "durationMs": clip.duration_ms,
                "attempt": attempt,
            }
        )
        self._audio.play(clip, abort)
        if abort.is_set():
            return 0.0
        self._audio.countdown(
            self._config.countdown_seconds,
            abort,
            lambda remaining: self._hub.publish({"type": "countdown", "n": remaining}),
        )
        if abort.is_set():
            return 0.0
        self._hub.publish({"type": "recording", "livePeaks": [None] * _COLUMNS})

        def on_peaks(peaks: list[float | None]) -> None:
            self._hub.publish({"type": "recording", "livePeaks": peaks})

        take = self._audio.record(clip.duration_ms, on_peaks, abort)
        if abort.is_set() or take.samples.size == 0:
            return 0.0
        percent = self._scorer.percent(clip, take)
        self._hub.publish(
            {
                "type": "result",
                "percent": percent,
                "passed": percent >= self._config.threshold_percent,
            }
        )
        return percent

    @staticmethod
    def _hold(abort: threading.Event) -> None:
        deadline = time.monotonic() + _RESULT_HOLD_SECONDS
        while time.monotonic() < deadline:
            if abort.is_set():
                return
            time.sleep(0.05)

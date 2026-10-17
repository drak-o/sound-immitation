"""Play reference clips, count down, and record the microphone."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample as scipy_resample

# Horizontal buckets on the overlay waveform. Not samples, and not samples per second.
OVERLAY_COLUMN_COUNT = 400
_AUDIO_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3"}


@dataclass
class Clip:
    samples: np.ndarray
    sample_rate: int
    duration_ms: int
    peaks: list[float]


@dataclass
class Take:
    samples: np.ndarray
    sample_rate: int
    peaks: list[float | None]


def resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float64)
    if audio.size == 0 or source_rate == target_rate:
        return audio
    target_length = max(1, int(round(audio.size * target_rate / source_rate)))
    return scipy_resample(audio, target_length)


def waveform_columns(
    samples: np.ndarray, filled_ratio: float = 1.0
) -> list[float | None]:
    """Peak columns on one shared timeline.

    A partial take fills only the left-hand columns. Column i is the same
    slice of the full duration for both the reference and the live take.
    """
    columns: list[float | None] = [None] * OVERLAY_COLUMN_COUNT
    count = int(samples.shape[0])
    if count == 0 or filled_ratio <= 0:
        return columns
    filled = (
        OVERLAY_COLUMN_COUNT
        if filled_ratio >= 1
        else int(filled_ratio * OVERLAY_COLUMN_COUNT)
    )
    if filled <= 0:
        return columns
    peaks = np.zeros(filled, dtype=np.float64)
    for index in range(filled):
        start = int(index * count / filled)
        end = max(start + 1, int((index + 1) * count / filled))
        peaks[index] = float(np.max(np.abs(samples[start:end])))
    scale = float(peaks.max())
    if scale > 1e-8:
        peaks /= scale
    for index, value in enumerate(peaks):
        columns[index] = float(value)
    return columns


def _load_samples(path: Path) -> tuple[np.ndarray, int]:
    if path.suffix.lower() == ".mp3":
        import miniaudio

        decoded = miniaudio.decode_file(
            str(path),
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1,
            sample_rate=44100,
        )
        samples = np.array(decoded.samples, dtype=np.float32)
        return samples, int(decoded.sample_rate)

    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    samples = data.mean(axis=1).astype(np.float32, copy=False)
    return samples, int(rate)


class AudioSession:
    def __init__(self, sounds_dir: Path, countdown_sound: Path | None) -> None:
        self._sounds_dir = sounds_dir
        if countdown_sound is None:
            # 40 ms beep at 48 kHz, used only when countdown_sound is null.
            rate = 48000
            count = int(rate * 0.04)
            time_axis = np.arange(count, dtype=np.float64) / rate
            envelope = np.exp(-time_axis * 40)
            wave = 0.4 * np.sin(2 * np.pi * 1000 * time_axis) * envelope
            self._tick_samples = wave.astype(np.float32)
            self._tick_rate = rate
        else:
            if not countdown_sound.is_file():
                raise SystemExit(f"Countdown sound does not exist: {countdown_sound}")
            samples, rate = _load_samples(countdown_sound)
            # Cut at 0.3 seconds so the beep finishes inside the one-second gap.
            limit = max(1, int(rate * 0.3))
            self._tick_samples = samples[:limit]
            self._tick_rate = rate

    def pick_random(self) -> Clip:
        directory = self._sounds_dir
        if not directory.is_dir():
            raise SystemExit(f"Sounds directory does not exist: {directory}")
        files = [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
        ]
        if not files:
            raise SystemExit(f"No audio files in {directory}")
        path = random.choice(files)
        samples, rate = _load_samples(path)
        if samples.size == 0 or rate <= 0:
            raise SystemExit(f"Could not read audio from {path}")
        # Cut the quiet lead-in. 2% of the peak, held for 10 ms, is the start of
        # the sound, so playback begins on the countdown instead of after a gap.
        peak = float(np.max(np.abs(samples)))
        window = max(1, int(rate * 0.01))
        if peak > 1e-8 and samples.size > window:
            amplitude = np.abs(samples.astype(np.float64))
            cumulative = np.cumsum(amplitude)
            level = (
                cumulative[window - 1 :] - np.concatenate([[0.0], cumulative[:-window]])
            ) / window
            loud = np.flatnonzero(level >= peak * 0.02)
            if loud.size:
                samples = samples[int(loud[0]) :]
        duration_ms = max(1, int(round(samples.shape[0] / rate * 1000)))
        peaks = [
            value if value is not None else 0.0 for value in waveform_columns(samples)
        ]
        return Clip(
            samples=samples, sample_rate=rate, duration_ms=duration_ms, peaks=peaks
        )

    def countdown(
        self,
        seconds: int,
        abort: threading.Event,
        on_tick: Callable[[int], None] | None = None,
    ) -> None:
        for remaining in range(seconds, 0, -1):
            if abort.is_set():
                return
            if on_tick is not None:
                on_tick(remaining)
            started = time.monotonic()
            self.play(self._tick_samples, self._tick_rate, abort)
            # Finish the rest of this one-second gap. Abort is checked 20 times a second.
            deadline = time.monotonic() + max(0.0, 1.0 - (time.monotonic() - started))
            while time.monotonic() < deadline:
                if abort.is_set():
                    return
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def play(
        self, samples: np.ndarray, sample_rate: int, abort: threading.Event
    ) -> None:
        if samples.size == 0 or abort.is_set():
            return
        try:
            # Windows default output device.
            out_rate = int(
                round(float(sd.query_devices(kind="output")["default_samplerate"]))
            )
            audio = resample(samples, sample_rate, out_rate).astype(
                np.float32, copy=False
            )
            # 0.05 seconds of audio per write. Abort is checked 20 times a second.
            chunk = max(1, int(out_rate * 0.05))
            with sd.OutputStream(
                samplerate=out_rate,
                channels=1,
                dtype="float32",
                latency="low",
            ) as stream:
                position = 0
                while position < audio.shape[0]:
                    if abort.is_set():
                        stream.abort()
                        return
                    end = min(position + chunk, audio.shape[0])
                    stream.write(
                        np.ascontiguousarray(audio[position:end].reshape(-1, 1))
                    )
                    position = end
        except sd.PortAudioError as error:
            raise SystemExit(f"Playback failed: {error}") from error

    def record(
        self,
        duration_ms: int,
        on_peaks: Callable[[list[float | None]], None],
        abort: threading.Event,
    ) -> Take:
        try:
            # Windows default input device.
            in_rate = int(
                round(float(sd.query_devices(kind="input")["default_samplerate"]))
            )
            frames_total = max(1, int(round(in_rate * duration_ms / 1000)))
            # 0.05 seconds of audio per read. Abort is checked 20 times a second.
            chunk = max(1, int(in_rate * 0.05))
            collected = np.empty(frames_total, dtype=np.float32)
            captured = 0
            with sd.InputStream(
                samplerate=in_rate,
                channels=1,
                dtype="float32",
                latency="low",
            ) as stream:
                while captured < frames_total:
                    if abort.is_set():
                        break
                    frames = min(chunk, frames_total - captured)
                    data, _overflowed = stream.read(frames)
                    mono = np.asarray(data, dtype=np.float32).reshape(-1)[:frames]
                    collected[captured : captured + mono.shape[0]] = mono
                    captured += int(mono.shape[0])
                    on_peaks(
                        waveform_columns(collected[:captured], captured / frames_total)
                    )
        except sd.PortAudioError as error:
            raise SystemExit(f"Recording failed: {error}") from error
        samples = collected[:captured].copy()
        return Take(
            samples=samples,
            sample_rate=in_rate,
            peaks=waveform_columns(
                samples, 1.0 if captured >= frames_total else captured / frames_total
            ),
        )

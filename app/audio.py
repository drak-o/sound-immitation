"""Play reference clips, count down, and record the microphone."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample as scipy_resample

COLUMNS = 400
_CHUNK_SECONDS = 0.05
_TICK_LIMIT_SECONDS = 0.3
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


def waveform_columns(samples: np.ndarray, filled_ratio: float = 1.0) -> list[float | None]:
    """Peak columns on one shared timeline.

    A partial take fills only the left-hand columns. Column i is the same
    slice of the full duration for both the reference and the live take.
    """
    columns: list[float | None] = [None] * COLUMNS
    count = int(samples.shape[0])
    if count == 0 or filled_ratio <= 0:
        return columns
    filled = COLUMNS if filled_ratio >= 1 else int(filled_ratio * COLUMNS)
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


def _find_device(name: str | None, kind: str) -> int | None:
    if name is None:
        return None
    channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
    substring_matches: list[int] = []
    for index, device in enumerate(sd.query_devices()):
        if int(device[channel_key]) < 1:
            continue
        device_name = str(device["name"])
        if device_name.lower() == name.lower():
            return index
        if name.lower() in device_name.lower():
            substring_matches.append(index)
    if len(substring_matches) == 1:
        return substring_matches[0]
    if len(substring_matches) > 1:
        names = ", ".join(str(sd.query_devices(index)["name"]) for index in substring_matches)
        raise SystemExit(f"Multiple {kind} devices match {name!r}: {names}")
    raise SystemExit(f"No {kind} device matching {name!r}. Run python main.py --list-devices.")


def _device_rate(device: int | None, kind: str) -> tuple[int | None, int]:
    info = sd.query_devices(device, kind)
    return device, int(round(float(info["default_samplerate"])))


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


def _synthesized_tick() -> tuple[np.ndarray, int]:
    rate = 48000
    count = int(rate * 0.04)
    time_axis = np.arange(count, dtype=np.float64) / rate
    envelope = np.exp(-time_axis * 40)
    wave = (0.4 * np.sin(2 * np.pi * 1000 * time_axis) * envelope).astype(np.float32)
    return wave, rate


class AudioSession:
    def __init__(
        self,
        input_device: str | None,
        output_device: str | None,
        countdown_sound: Path | None,
    ) -> None:
        self._input_name = input_device
        self._output_name = output_device
        self._tick_samples, self._tick_rate = self._load_tick(countdown_sound)

    @staticmethod
    def list_devices() -> None:
        default_input, default_output = sd.default.device
        print(f"default input={default_input} output={default_output}")
        for index, device in enumerate(sd.query_devices()):
            print(
                f"{index}: {device['name']} in={device['max_input_channels']} "
                f"out={device['max_output_channels']} rate={device['default_samplerate']}"
            )

    def pick_random(self, directory: Path) -> Clip:
        if not directory.is_dir():
            raise SystemExit(f"Sounds directory does not exist: {directory}")
        files = [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
        ]
        if not files:
            raise SystemExit(f"No audio files in {directory}")
        return self._load_clip(random.choice(files))

    def play(self, clip: Clip, abort: object) -> None:
        self._play(clip.samples, clip.sample_rate, abort)

    def countdown(self, seconds: int, abort: object, on_tick: Callable[[int], None] | None = None) -> None:
        for remaining in range(seconds, 0, -1):
            if _aborted(abort):
                return
            if on_tick is not None:
                on_tick(remaining)
            started = time.monotonic()
            self._play(self._tick_samples, self._tick_rate, abort)
            self._wait(max(0.0, 1.0 - (time.monotonic() - started)), abort)

    def record(
        self,
        duration_ms: int,
        on_peaks: Callable[[list[float | None]], None],
        abort: object,
    ) -> Take:
        device, in_rate = _device_rate(_find_device(self._input_name, "input"), "input")
        frames_total = max(1, int(round(in_rate * duration_ms / 1000)))
        chunk = max(1, int(in_rate * _CHUNK_SECONDS))
        collected = np.empty(frames_total, dtype=np.float32)
        captured = 0
        try:
            with sd.InputStream(
                samplerate=in_rate,
                channels=1,
                dtype="float32",
                device=device,
                latency="low",
            ) as stream:
                while captured < frames_total:
                    if _aborted(abort):
                        break
                    frames = min(chunk, frames_total - captured)
                    data, _overflowed = stream.read(frames)
                    mono = np.asarray(data, dtype=np.float32).reshape(-1)[:frames]
                    collected[captured : captured + mono.shape[0]] = mono
                    captured += int(mono.shape[0])
                    on_peaks(waveform_columns(collected[:captured], captured / frames_total))
        except sd.PortAudioError as error:
            raise SystemExit(f"Recording failed: {error}") from error
        samples = collected[:captured].copy()
        return Take(
            samples=samples,
            sample_rate=in_rate,
            peaks=waveform_columns(samples, 1.0 if captured >= frames_total else captured / frames_total),
        )

    def _load_clip(self, path: Path) -> Clip:
        samples, rate = _load_samples(path)
        if samples.size == 0 or rate <= 0:
            raise SystemExit(f"Could not read audio from {path}")
        duration_ms = max(1, int(round(samples.shape[0] / rate * 1000)))
        peaks = [value if value is not None else 0.0 for value in waveform_columns(samples)]
        return Clip(samples=samples, sample_rate=rate, duration_ms=duration_ms, peaks=peaks)

    def _load_tick(self, path: Path | None) -> tuple[np.ndarray, int]:
        if path is None:
            return _synthesized_tick()
        if not path.is_file():
            raise SystemExit(f"Countdown sound does not exist: {path}")
        samples, rate = _load_samples(path)
        limit = max(1, int(rate * _TICK_LIMIT_SECONDS))
        return samples[:limit], rate

    def _play(self, samples: np.ndarray, sample_rate: int, abort: object) -> None:
        if samples.size == 0 or _aborted(abort):
            return
        device, out_rate = _device_rate(_find_device(self._output_name, "output"), "output")
        audio = resample(samples, sample_rate, out_rate).astype(np.float32, copy=False)
        chunk = max(1, int(out_rate * _CHUNK_SECONDS))
        try:
            with sd.OutputStream(
                samplerate=out_rate,
                channels=1,
                dtype="float32",
                device=device,
                latency="low",
            ) as stream:
                position = 0
                while position < audio.shape[0]:
                    if _aborted(abort):
                        stream.abort()
                        return
                    end = min(position + chunk, audio.shape[0])
                    stream.write(np.ascontiguousarray(audio[position:end].reshape(-1, 1)))
                    position = end
        except sd.PortAudioError as error:
            raise SystemExit(f"Playback failed: {error}") from error

    @staticmethod
    def _wait(duration: float, abort: object) -> None:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if _aborted(abort):
                return
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _aborted(abort: object) -> bool:
    return bool(getattr(abort, "is_set", lambda: False)())

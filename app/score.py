"""Time-aligned spectral similarity, as a percentage."""

from __future__ import annotations

import numpy as np

from app.audio import Clip, Take, resample

_TARGET_RATE = 16000
_FRAME_SAMPLES = int(_TARGET_RATE * 0.025)
_HOP_SAMPLES = int(_TARGET_RATE * 0.010)
_BAND_COUNT = 8
# 10 ms frames. 80 ms of warp: a small slip still matches, a late start does not.
_SLACK_FRAMES = 8
# Eight log-spaced bands from 80 Hz to 7.6 kHz. A tap fills every band.
_BAND_EDGES_HZ = np.geomspace(80.0, 7600.0, _BAND_COUNT + 1)
_BIN_FREQS_HZ = np.fft.rfftfreq(_FRAME_SAMPLES, d=1.0 / _TARGET_RATE)
_BAND_BINS: list[np.ndarray] = []
for _band in range(_BAND_COUNT):
    _low = _BAND_EDGES_HZ[_band]
    _high = _BAND_EDGES_HZ[_band + 1]
    _upper = (
        _BIN_FREQS_HZ <= _high if _band == _BAND_COUNT - 1 else _BIN_FREQS_HZ < _high
    )
    _BAND_BINS.append(np.flatnonzero((_BIN_FREQS_HZ >= _low) & _upper))
# Hann window so a tone stays in its bands instead of leaking into all of them.
_WINDOW = np.hanning(_FRAME_SAMPLES)


class Scorer:
    def percent(self, clip: Clip, take: Take) -> float:
        reference = _frame_spectra(
            resample(clip.samples, clip.sample_rate, _TARGET_RATE)
        )
        recorded = _frame_spectra(
            resample(take.samples, take.sample_rate, _TARGET_RATE)
        )
        reference = _band_distribution(reference)
        recorded = _band_distribution(recorded)
        if recorded.shape[0] == 0 or reference.shape[0] == 0:
            print("similarity=0.0000 percent=0.0")
            return 0.0
        similarity = _dtw_similarity(reference, recorded)
        percent = round(max(0.0, similarity) * 100, 1)
        print(f"similarity={similarity:.4f} percent={percent}")
        return percent


def _frame_spectra(samples: np.ndarray) -> np.ndarray:
    """Eight band energies per 25 ms frame, hopped every 10 ms."""
    audio = np.asarray(samples, dtype=np.float64)
    if audio.size == 0:
        return np.zeros((0, _BAND_COUNT), dtype=np.float64)
    if audio.size < _FRAME_SAMPLES:
        padded = np.zeros(_FRAME_SAMPLES, dtype=np.float64)
        padded[: audio.size] = audio
        audio = padded
    count = 1 + (audio.size - _FRAME_SAMPLES) // _HOP_SAMPLES
    spectra = np.empty((count, _BAND_COUNT), dtype=np.float64)
    for index in range(count):
        start = index * _HOP_SAMPLES
        power = (
            np.abs(np.fft.rfft(audio[start : start + _FRAME_SAMPLES] * _WINDOW)) ** 2
        )
        for band, bins in enumerate(_BAND_BINS):
            spectra[index, band] = float(power[bins].sum()) if bins.size else 0.0
    return spectra


def _band_distribution(spectra: np.ndarray) -> np.ndarray:
    """Divide each frame by its band sum so loudness cannot create a match."""
    if spectra.size == 0:
        return spectra
    totals = spectra.sum(axis=1, keepdims=True)
    distributed = np.zeros_like(spectra)
    loud = totals[:, 0] > 1e-12
    distributed[loud] = spectra[loud] / totals[loud]
    return distributed


def _band_overlap(left: np.ndarray, right: np.ndarray) -> float:
    """Share of each frame's band energy that falls in the same bands.

    A breath covers every band. Cosine similarity still counts that as a
    match when the clip only uses some of them.
    """
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    # Two silent frames are the same shape. One silent frame matches nothing.
    if left_norm < 1e-12 or right_norm < 1e-12:
        return 1.0 if left_norm < 1e-12 and right_norm < 1e-12 else 0.0
    return float(np.minimum(left, right).sum())


def _dtw_similarity(reference: np.ndarray, take: np.ndarray) -> float:
    """Mean band overlap along an 80 ms Sakoe-Chiba band.

    The recording stays on the clip's timeline. Local cost is the unshared
    fraction of two 8-band frames.
    """
    ref = np.asarray(reference, dtype=np.float64)
    rec = np.asarray(take, dtype=np.float64)
    row_count = ref.shape[0]
    column_count = rec.shape[0]
    band = _SLACK_FRAMES
    cost = np.full((row_count + 1, column_count + 1), np.inf, dtype=np.float64)
    cost[0, 0] = 0.0
    for row in range(1, row_count + 1):
        center = int(row * column_count / row_count) or 1
        start = max(1, center - band)
        end = min(column_count, center + band)
        for column in range(start, end + 1):
            local = 1.0 - _band_overlap(ref[row - 1], rec[column - 1])
            cost[row, column] = local + min(
                cost[row - 1, column],
                cost[row, column - 1],
                cost[row - 1, column - 1],
            )
    row = row_count
    column = column_count
    similarities: list[float] = []
    while row > 0 and column > 0:
        similarities.append(_band_overlap(ref[row - 1], rec[column - 1]))
        steps = (
            (cost[row - 1, column - 1], row - 1, column - 1),
            (cost[row - 1, column], row - 1, column),
            (cost[row, column - 1], row, column - 1),
        )
        _step_cost, row, column = min(steps, key=lambda step: step[0])
    if not similarities:
        return 0.0
    return float(np.mean(similarities))

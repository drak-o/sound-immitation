"""Time-aligned spectral similarity, as a percentage."""

from __future__ import annotations

import math

import numpy as np

from app.audio import Clip, Take, resample

_TARGET_RATE = 16000
_FRAME_SAMPLES = int(_TARGET_RATE * 0.025)
_HOP_SAMPLES = int(_TARGET_RATE * 0.010)
_BAND_COUNT = 8
_BAND_RATIO = 0.2
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
        # Drop silent edges on the take only. 0.1% of its loudest frame is
        # silence. Keep an edge the reference shares, so a clip still matches
        # itself; drop extra silence before the reference has started.
        reference_energy = reference.sum(axis=1)
        recorded_energy = recorded.sum(axis=1)
        recorded_peak = float(recorded_energy.max()) if recorded_energy.size else 0.0
        reference_peak = float(reference_energy.max()) if reference_energy.size else 0.0
        if recorded_peak <= 1e-12:
            recorded = recorded[:0]
        else:
            take_quiet = recorded_energy < recorded_peak * 0.001
            clip_quiet = (
                reference_energy < reference_peak * 0.001
                if reference_peak > 1e-12
                else np.ones(reference_energy.shape[0], dtype=bool)
            )
            start = 0
            while (
                start < recorded.shape[0]
                and take_quiet[start]
                and (start >= clip_quiet.shape[0] or not clip_quiet[start])
            ):
                start += 1
            end = recorded.shape[0]
            while end > start:
                ref_index = clip_quiet.shape[0] - (recorded.shape[0] - (end - 1))
                reference_is_quiet = (
                    0 <= ref_index < clip_quiet.shape[0] and clip_quiet[ref_index]
                )
                if not take_quiet[end - 1] or reference_is_quiet:
                    break
                end -= 1
            recorded = recorded[start:end]
        reference = _band_distribution(reference)
        recorded = _band_distribution(recorded)
        if recorded.shape[0] == 0 or reference.shape[0] == 0:
            print("similarity=0.0000 percent=0.0")
            return 0.0
        similarity = _dtw_similarity(reference, recorded, _BAND_RATIO)
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


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    # Two silent frames are the same shape. One silent frame matches nothing.
    if left_norm < 1e-12 or right_norm < 1e-12:
        return 1.0 if left_norm < 1e-12 and right_norm < 1e-12 else 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def _dtw_similarity(
    reference: np.ndarray, take: np.ndarray, band_ratio: float
) -> float:
    """Mean cosine similarity along a 20% Sakoe-Chiba band.

    The band is widened to the diagonal step so a much shorter take can still
    reach the corner. Local cost is the cosine distance between 8-band frames.
    """
    ref = np.asarray(reference, dtype=np.float64)
    rec = np.asarray(take, dtype=np.float64)
    row_count = ref.shape[0]
    column_count = rec.shape[0]
    band = max(1, int(round(band_ratio * max(row_count, column_count))))
    band = max(
        band, math.ceil(max(row_count, column_count) / min(row_count, column_count))
    )
    cost = np.full((row_count + 1, column_count + 1), np.inf, dtype=np.float64)
    cost[0, 0] = 0.0
    for row in range(1, row_count + 1):
        center = int(row * column_count / row_count) or 1
        start = max(1, center - band)
        end = min(column_count, center + band)
        for column in range(start, end + 1):
            local = 1.0 - _cosine_similarity(ref[row - 1], rec[column - 1])
            cost[row, column] = local + min(
                cost[row - 1, column],
                cost[row, column - 1],
                cost[row - 1, column - 1],
            )
    row = row_count
    column = column_count
    similarities: list[float] = []
    while row > 0 and column > 0:
        similarities.append(_cosine_similarity(ref[row - 1], rec[column - 1]))
        steps = (
            (cost[row - 1, column - 1], row - 1, column - 1),
            (cost[row - 1, column], row - 1, column),
            (cost[row, column - 1], row, column - 1),
        )
        _step_cost, row, column = min(steps, key=lambda step: step[0])
    if not similarities:
        return 0.0
    return float(np.mean(similarities))

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
        reference_power = _frame_spectra(
            resample(clip.samples, clip.sample_rate, _TARGET_RATE)
        )
        recorded_power = _frame_spectra(
            resample(take.samples, take.sample_rate, _TARGET_RATE)
        )
        reference = _log_bands(reference_power)
        recorded = _log_bands(recorded_power)
        if recorded.shape[0] == 0 or reference.shape[0] == 0:
            print("similarity=0.0000 percent=0.0")
            return 0.0
        similarity = _dtw_similarity(reference, recorded)
        take_flat = float(np.median(_spectral_flatness(recorded_power)))
        # Herre, Allamanche, and Hellmuth, WASPAA 2001: flatness near 1 is
        # noise. Cosine only sees band direction, so the clipped breath
        # still scored 79% on spongebob. That breath measured 0.55–0.64.
        # Every clip is at most 0.20.
        if take_flat > 0.45:
            similarity = 0.0
        percent = round(max(0.0, similarity) * 100, 1)
        print(f"similarity={similarity:.4f} flatness={take_flat:.2f} percent={percent}")
        return percent


def _spectral_flatness(power: np.ndarray) -> np.ndarray:
    """Geometric mean over arithmetic mean of the eight bands, per frame.

    Herre, Allamanche, and Hellmuth, "Robust Matching of Audio Signals
    Using Spectral Flatness Features," Proc. WASPAA, pp. 127–130, 2001.
    Flatness near 1 is noise. Near 0 is tonal.
    """
    floored = np.maximum(power, 1e-20)
    geometric = np.exp(np.mean(np.log(floored), axis=1))
    arithmetic = np.mean(floored, axis=1)
    return geometric / np.maximum(arithmetic, 1e-20)


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


def _log_bands(spectra: np.ndarray) -> np.ndarray:
    """Mean-centered decibel band energies.

    Seyerlehner, Widmer, and Knees, "Frame Level Audio Similarity — A
    Codebook Approach," Proc. DAFx-08, Espoo, 2008, eq. 3,
    https://www.cp.jku.at/research/papers/Seyerlehner_etal_DAFx_2008.pdf
    X(k)dB = 20 log10(X(k)). A gain is a constant in the log domain, so
    subtracting the frame mean removes loudness. A frame whose band sum
    is below 1e-12 stays zero.
    """
    if spectra.size == 0:
        return spectra
    logged = np.zeros_like(spectra)
    totals = spectra.sum(axis=1)
    loud = totals > 1e-12
    if not np.any(loud):
        return logged
    peaks = spectra[loud].max(axis=1, keepdims=True)
    # 1e-6 of the peak. 20*log10(0) is undefined.
    floored = np.maximum(spectra[loud], peaks * 1e-6)
    decibels = 20.0 * np.log10(floored)
    logged[loud] = decibels - decibels.mean(axis=1, keepdims=True)
    return logged


def _band_cosine(left: np.ndarray, right: np.ndarray) -> float:
    """Cosine similarity of two mean-centered log-band frames.

    Foote, "Content-Based Retrieval of Music and Audio," Proc. SPIE 3229,
    pp. 138–147, 1997. Seyerlehner, Widmer, and Knees, DAFx-08, 2008,
    reference [10].

    Histogram intersection is not used. On equal-sum histograms it is half
    an L1 distance (Seyerlehner et al. 2008, eq. 6–7), the measure from
    Swain and Ballard, "Color Indexing," Int. J. Computer Vision 7(1),
    pp. 11–32, 1991.
    """
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    # Two silent frames are the same shape. One silent frame matches nothing.
    if left_norm < 1e-12 or right_norm < 1e-12:
        return 1.0 if left_norm < 1e-12 and right_norm < 1e-12 else 0.0
    return max(0.0, float(np.dot(left, right) / (left_norm * right_norm)))


def _dtw_similarity(reference: np.ndarray, take: np.ndarray) -> float:
    """Mean cosine similarity along an 80 ms Sakoe-Chiba band.

    The recording stays on the clip's timeline. Local cost is one minus
    the cosine similarity of two log-band frames.
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
            local = 1.0 - _band_cosine(ref[row - 1], rec[column - 1])
            cost[row, column] = local + min(
                cost[row - 1, column],
                cost[row, column - 1],
                cost[row - 1, column - 1],
            )
    row = row_count
    column = column_count
    similarities: list[float] = []
    while row > 0 and column > 0:
        similarities.append(_band_cosine(ref[row - 1], rec[column - 1]))
        steps = (
            (cost[row - 1, column - 1], row - 1, column - 1),
            (cost[row - 1, column], row - 1, column),
            (cost[row, column - 1], row, column - 1),
        )
        _step_cost, row, column = min(steps, key=lambda step: step[0])
    if not similarities:
        return 0.0
    return float(np.mean(similarities))

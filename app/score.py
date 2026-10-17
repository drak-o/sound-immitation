"""Time-aligned envelope similarity, as a percentage."""

from __future__ import annotations

import math

import numpy as np

from app.audio import Clip, Take, resample

_TARGET_RATE = 16000
_FRAME_SAMPLES = int(_TARGET_RATE * 0.025)
_HOP_SAMPLES = int(_TARGET_RATE * 0.010)
_SILENCE = 0.05
_BAND_RATIO = 0.2


class Scorer:
    def percent(self, clip: Clip, take: Take) -> float:
        reference = _envelope(resample(clip.samples, clip.sample_rate, _TARGET_RATE))
        recorded = _envelope(resample(take.samples, take.sample_rate, _TARGET_RATE))
        reference = _peak_normalize(reference)
        recorded = _trim_edges(_peak_normalize(recorded), _SILENCE)
        if recorded.size < 3 or reference.size < 3:
            print("correlation=0.0000 mae=1.0000 percent=0.0")
            return 0.0
        warped_reference, warped_take = _dtw_align(reference, recorded, _BAND_RATIO)
        correlation = _pearson(warped_reference, warped_take)
        mae = float(np.mean(np.abs(warped_reference - warped_take)))
        percent = round(max(0.0, correlation) * 100, 1)
        print(f"correlation={correlation:.4f} mae={mae:.4f} percent={percent}")
        return percent


def _envelope(samples: np.ndarray) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float64)
    if audio.size < _FRAME_SAMPLES:
        if audio.size == 0:
            return np.zeros(0, dtype=np.float64)
        return np.array([math.sqrt(float(np.mean(audio * audio)))], dtype=np.float64)
    count = 1 + (audio.size - _FRAME_SAMPLES) // _HOP_SAMPLES
    frames = np.empty(count, dtype=np.float64)
    for index in range(count):
        start = index * _HOP_SAMPLES
        window = audio[start : start + _FRAME_SAMPLES]
        frames[index] = math.sqrt(float(np.mean(window * window)))
    return frames


def _peak_normalize(frames: np.ndarray) -> np.ndarray:
    if frames.size == 0:
        return frames
    peak = float(np.max(frames))
    if peak <= 1e-8:
        return np.zeros_like(frames)
    return frames / peak


def _trim_edges(frames: np.ndarray, threshold: float) -> np.ndarray:
    loud = np.flatnonzero(frames >= threshold)
    if loud.size == 0:
        return frames[:0]
    return frames[int(loud[0]) : int(loud[-1]) + 1]


def _dtw_align(reference: np.ndarray, take: np.ndarray, band_ratio: float) -> tuple[np.ndarray, np.ndarray]:
    """Warp both envelopes onto one path.

    The band is 20% of the longer envelope around the diagonal. It is widened
    to the diagonal step so a much shorter take can still reach the corner.
    """
    ref = np.asarray(reference, dtype=np.float64)
    rec = np.asarray(take, dtype=np.float64)
    row_count = ref.shape[0]
    column_count = rec.shape[0]
    band = max(1, int(round(band_ratio * max(row_count, column_count))))
    band = max(band, math.ceil(max(row_count, column_count) / min(row_count, column_count)))
    cost = np.full((row_count + 1, column_count + 1), np.inf, dtype=np.float64)
    cost[0, 0] = 0.0
    for row in range(1, row_count + 1):
        center = int(row * column_count / row_count) or 1
        start = max(1, center - band)
        end = min(column_count, center + band)
        for column in range(start, end + 1):
            local = abs(ref[row - 1] - rec[column - 1])
            cost[row, column] = local + min(
                cost[row - 1, column],
                cost[row, column - 1],
                cost[row - 1, column - 1],
            )
    row = row_count
    column = column_count
    pairs: list[tuple[int, int]] = []
    while row > 0 and column > 0:
        pairs.append((row - 1, column - 1))
        steps = (
            (cost[row - 1, column - 1], row - 1, column - 1),
            (cost[row - 1, column], row - 1, column),
            (cost[row, column - 1], row, column - 1),
        )
        _step_cost, row, column = min(steps, key=lambda step: step[0])
    pairs.reverse()
    warped_reference = np.array([ref[left] for left, _right in pairs], dtype=np.float64)
    warped_take = np.array([rec[right] for _left, right in pairs], dtype=np.float64)
    return warped_reference, warped_take


def _pearson(left: np.ndarray, right: np.ndarray) -> float:
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    left_norm = float(np.linalg.norm(left_centered))
    right_norm = float(np.linalg.norm(right_centered))
    # A steady tone has a flat envelope. Pearson of that leftover ripple is
    # numerical noise; closeness of the two levels is the actual match.
    if left_norm < 1e-3 or right_norm < 1e-3:
        return max(0.0, 1.0 - float(np.mean(np.abs(left - right))))
    return float(np.dot(left_centered, right_centered) / (left_norm * right_norm))

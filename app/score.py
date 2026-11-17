"""Mean per-frame loudness ratio, as a percentage."""

from __future__ import annotations

import numpy as np

from app.audio import Clip, Take, GENERAL_RATE, resample


class Scorer:
    def percent(self, clip: Clip, take: Take) -> float:
        actual = _loudness(resample(clip.samples, clip.sample_rate, GENERAL_RATE))
        imitation = _loudness(resample(take.samples, take.sample_rate, GENERAL_RATE))
        # Frame 1 of the imitation against frame 1 of the actual sound.
        count = min(actual.size, imitation.size)
        if count == 0:
            return 0.0
        actual = actual[:count]
        imitation = imitation[:count]
        # Both silent is zero over zero. Counting it as a match would let a
        # silent imitation score the quiet fraction of the actual sound.
        heard = np.maximum(actual, imitation) > 0
        if not np.any(heard):
            return 0.0
        ratio = np.minimum(actual[heard], imitation[heard]) / np.maximum(
            actual[heard], imitation[heard]
        )
        return round(float(np.mean(ratio)) * 100, 1)


def _loudness(audio: np.ndarray) -> np.ndarray:
    """Mean absolute level of each 10 ms frame.

    Rabiner and Sambur, "An Algorithm for Determining the Endpoints of
    Isolated Utterances," Bell System Technical Journal, vol. 54, no. 2,
    pp. 297–315, Feb. 1975.
    https://ieeexplore.ieee.org/document/6778857
    Their frame energy is the sum of absolute samples over 10 ms. The mean
    is that sum divided by the fixed frame length. They use the energy to
    find endpoints. Here it is the whole description of the sound.
    """
    samples = np.asarray(audio, dtype=np.float64)
    frame = int(GENERAL_RATE * 0.01)
    usable = samples.size - (samples.size % frame)
    if usable < frame:
        return np.zeros(0, dtype=np.float64)
    return np.mean(np.abs(samples[:usable]).reshape(-1, frame), axis=1)

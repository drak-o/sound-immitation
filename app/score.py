"""Mean per-frame loudness ratio, as a percentage."""

from __future__ import annotations

import numpy as np

from app.audio import Clip, Take, GENERAL_RATE, resample


class Scorer:
    def percent(self, clip: Clip, take: Take) -> float:
        actual = _loudness(resample(clip.samples, clip.sample_rate, GENERAL_RATE))
        imitation = _loudness(resample(take.samples, take.sample_rate, GENERAL_RATE))
        ratio = np.minimum(actual, imitation) / np.maximum(actual, imitation) # min-max normalization, values in 0,1 range
        return round(float(np.mean(ratio)) * 100, 1) # mean of the per frame ratios as a percentage


def _loudness(audio: np.ndarray) -> np.ndarray:
    """Sum of absolute samples in each 10 ms frame.

    Rabiner and Sambur, "An Algorithm for Determining the Endpoints of
    Isolated Utterances," Bell System Technical Journal, vol. 54, no. 2,
    pp. 297–315, Feb. 1975., equation 1
    https://ieeexplore.ieee.org/document/6778857
    Equation 1 is that sum over 10 ms. At their 10 kHz rate, 10 ms is 100
    samples, and the paper does not consider another sample rate. Here the
    frame length is the sample rate times 10 ms, which is 160 samples. They
    center the window because each sum is stored at one time, and that time
    is the middle of the 10 ms that was added. Here the energy is the whole
    description of the sound. Frame i of the clip is compared with frame i 
	of the take, both featuring the same sample rate and time grid
	, so we need no centring.
    """
    samples_in_10ms = int(GENERAL_RATE * 0.01)
    whole = audio.size // samples_in_10ms * samples_in_10ms # round down to the nearest multiple of samples_in_10ms
    return np.sum(np.abs(audio[:whole]).reshape(-1, samples_in_10ms), axis=1)

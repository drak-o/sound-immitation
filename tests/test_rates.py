"""Eight imitation cases. FAR, FRR, and EER are derived from their scores.

A plausible imitation is a microphone take in tests/recordings/ named the
same as the clip. It is a genuine pair: a person making the clip, expected
to pass.
Breathing and tapping are one file each in tests/recordings/, named
breathing and tapping. Each is an incorrect pair against every clip. Pass
is a score of 50 or higher.
Each trial is written to tests/battery.log as the percent and the booleans
predicted and actual. Actual is true when the percent is 50 or higher.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
# The script's directory is tests/, so the working tree has to be on the path.
sys.path.insert(0, str(ROOT))

from app.audio import Clip, Take, _load_samples
from app.score import Scorer

# Pass is 50. A correct pair below the line is a false rejection.
PASS_PERCENT = 50.0
_AUDIO_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3"}

# idk about genuine and impostor might be wrong
_GENUINE: list[float] = []
_IMPOSTOR: list[float] = []
_CLIPS: list[tuple[str, np.ndarray, int, Clip]] = []
_RECORDINGS: dict[str, Path] = {}
_SCORER = Scorer()


def _rates(genuine, impostor, threshold):
    false_rejections = sum(score < threshold for score in genuine)
    false_acceptances = sum(score >= threshold for score in impostor)
    return (
        100.0 * false_acceptances / len(impostor),
        100.0 * false_rejections / len(genuine),
        false_acceptances,
        false_rejections,
    )


def _eer(genuine: list[float], impostor: list[float]) -> tuple[float, float]:
    """Error rate where FAR and FRR are closest. Describing the quality of the model.

    Rates stay constant between scores. One call per distinct score, plus
    100 so the stretch above the last score is included. The reported
    threshold is the first tenth of that stretch.

    optimization:
    - no more 1000 step loop calling _rates function
    """
    cutoffs = sorted(
        {
            int(round(score * 10)) for score in genuine + impostor
        }  # convert score from percent to tenths
    )
    best_threshold = 0.0
    best_gap = float("inf")
    best_rate = 0.0
    previous = -1
    for cutoff in cutoffs:
        false_acceptance_rate, false_rejection_rate, _, _ = _rates(
            genuine, impostor, cutoff / 10
        )
        gap = abs(false_acceptance_rate - false_rejection_rate)
        # Tenths are integers here. 769 is 76.9, and the stretch below 84.2
        # starts at 77.0.
        start = 0.0 if previous < 0 else (previous + 1) / 10
        if gap < best_gap:
            best_gap = gap
            best_threshold = start
            best_rate = (false_acceptance_rate + false_rejection_rate) / 2
        previous = cutoff
    return best_rate, best_threshold


def _score(
    stem: str, case: str, clip: Clip, samples: np.ndarray, rate: int, predicted: bool
) -> None:
    """The percent is kept for the rates."""
    take = Take(samples=np.asarray(samples), sample_rate=rate)
    percent = _SCORER.percent(clip, take)

    actual = percent >= PASS_PERCENT
    scores = _GENUINE if predicted else _IMPOSTOR
    scores.append(percent)

    # pure flat sound / faaah: 10.7 predicted=False actual=False
    print(f"{case} / {stem}: {percent} predicted={predicted} actual={actual}")


def _shared(name: str) -> tuple[np.ndarray, int]:
    path = _RECORDINGS.get(name)
    if path is None:
        print(f"missing {name}")
        raise unittest.SkipTest(f"missing {name}")
    return _load_samples(path)


def setUpModule() -> None:
    sounds = ROOT / "sounds"
    if not sounds.is_dir():
        raise RuntimeError(f"Sounds directory does not exist: {sounds}")
    clips = [
        path
        for path in sounds.iterdir()
        if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
    ]
    if not clips:
        raise RuntimeError(f"No audio files in {sounds}")
    # Every print in this run is a battery.log line. Unittest progress stays on stderr.
    sys.stdout = open(
        ROOT / "tests" / "battery.log", "w", encoding="utf-8", buffering=1
    )
    _GENUINE.clear()
    _IMPOSTOR.clear()
    _CLIPS.clear()
    _RECORDINGS.clear()

    # Load recordings from tests/recordings/ into _RECORDINGS 
    recordings = ROOT / "tests" / "recordings"
    if recordings.is_dir():
        for path in recordings.iterdir():
            if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS:
                _RECORDINGS[path.stem] = path

    # Load clips from sounds/ into _CLIPS
    for path in clips:
        samples, rate = _load_samples(path)
        duration_ms = max(1, int(round(samples.shape[0] / rate * 1000)))
        clip = Clip(
            samples=samples, sample_rate=rate, duration_ms=duration_ms, peaks=[]
        )
        _CLIPS.append((path.stem, samples, rate, clip))


def tearDownModule() -> None:
    """
    revision d014655 testing-refactor-wip
    genuine=9 impostor=15
    FAR=46.7 (7/15) at 50
    FRR=11.1 (1/9) at 50
    EER=24.4 at 57.7
    """
    try:
        if _GENUINE and _IMPOSTOR:
            false_acceptance_rate, false_rejection_rate, acceptances, rejections = (
                _rates(_GENUINE, _IMPOSTOR, PASS_PERCENT)
            )
            equal_error_rate, threshold = _eer(_GENUINE, _IMPOSTOR)
            revision = subprocess.check_output(
                ["git", "log", "-1", "--format=%h %s"], cwd=ROOT, text=True
            ).strip()
            print()
            print(f"revision {revision}")
            print(f"genuine={len(_GENUINE)} impostor={len(_IMPOSTOR)}")
            print(
                f"FAR={false_acceptance_rate:.1f} ({acceptances}/{len(_IMPOSTOR)})"
                f" at {PASS_PERCENT:.0f}"
            )
            print(
                f"FRR={false_rejection_rate:.1f} ({rejections}/{len(_GENUINE)})"
                f" at {PASS_PERCENT:.0f}"
            )
            print(f"EER={equal_error_rate:.1f} at {threshold:.1f}")
    finally:
        sys.stdout.close()
        sys.stdout = sys.__stdout__


class ImitationTest(unittest.TestCase):
    def test_nothing(self) -> None:
        for stem, samples, rate, clip in _CLIPS:
            _score(stem, "nothing", clip, np.zeros_like(samples), rate, False)

    def test_same_sound(self) -> None:
        for stem, samples, rate, clip in _CLIPS:
            _score(stem, "the same sound", clip, samples, rate, True)

    def test_plausible(self) -> None:
        found = False
        for stem, _, _, clip in _CLIPS:
            recording = _RECORDINGS.get(stem)
            if recording is None:
                print(f"missing {stem}")
                continue
            found = True
            recorded, recorded_rate = _load_samples(recording)
            _score(stem, "plausible", clip, recorded, recorded_rate, True)
        if not found:
            self.skipTest("missing plausible imitation")

    def test_rhythmical_tapping(self) -> None:
        recorded, recorded_rate = _shared("tapping")
        for stem, _, _, clip in _CLIPS:
            _score(stem, "tapping", clip, recorded, recorded_rate, False)

    def test_pure_flat_sound(self) -> None:
        for stem, samples, rate, clip in _CLIPS:
            # 440 Hz tone of the same length. A steady tone is a different sound.
            time_axis = np.arange(samples.shape[0], dtype=np.float64) / rate
            tone = (0.2 * np.sin(2 * np.pi * 440.0 * time_axis)).astype(np.float32)
            _score(stem, "pure flat sound", clip, tone, rate, False)

    def test_breathing(self) -> None:
        recorded, recorded_rate = _shared("breathing")
        for stem, _, _, clip in _CLIPS:
            _score(stem, "breathing", clip, recorded, recorded_rate, False)

    def test_same_sound_added_noise(self) -> None:
        for stem, samples, rate, clip in _CLIPS:
            # 0.01 standard deviation is about -40 dB of hiss.
            noise = np.random.default_rng(0).normal(0.0, 0.01, samples.shape)
            noisy = (samples + noise).astype(np.float32)
            _score(stem, "the same sound, added noise", clip, noisy, rate, True)

    def test_same_sound_started_late(self) -> None:
        for stem, samples, rate, clip in _CLIPS:
            # 200 ms of silence in front. That is past the 80 ms warp. The end
            # is trimmed so the take stays the length of the clip.
            shift = int(round(rate * 0.2))
            late = np.concatenate([np.zeros(shift, dtype=samples.dtype), samples])[
                : samples.shape[0]
            ]
            _score(stem, "the same sound, started late", clip, late, rate, False)


if __name__ == "__main__":
    unittest.main()

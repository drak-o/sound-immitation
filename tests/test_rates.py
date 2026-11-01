"""Eight imitation cases. FAR, FRR, and EER are derived from their scores.

A plausible imitation is a microphone take under
tests/recordings/<clip stem>/plausible/. It is a genuine pair: a person
making the clip, expected to pass.
Breathing and tapping are one file each in tests/recordings/, named
breathing and tapping. Each is an incorrect pair against every clip. Pass
is a score of 50 or higher.
Each trial is written to tests/battery.log as the percent, the predicted
Pass or Fail, and the actual Pass or Fail at 50. The terminal prints one
line per revision: the commit and its FAR, FRR, and EER. The same cases
then run for every commit that changed app/score.py.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from pathlib import Path
from unittest.runner import TextTestRunner, registerResult

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
# An older revision is loaded from BATTERY_APP. Otherwise this is the working tree.
if os.environ.get("BATTERY_APP"):
    sys.path.insert(0, os.environ["BATTERY_APP"])
else:
    sys.path.insert(0, str(ROOT))

from app.audio import Clip, Take
from app.score import Scorer


def _run_without_progress(self, test):
    """The terminal is one rates line per commit. Trials are written to the log."""
    result = self._makeResult()
    registerResult(result)
    result.failfast = self.failfast
    result.buffer = self.buffer
    result.tb_locals = self.tb_locals
    result.dots = False
    result.showAll = False
    with warnings.catch_warnings():
        if self.warnings:
            warnings.simplefilter(self.warnings)
        start_test_run = getattr(result, "startTestRun", None)
        if start_test_run is not None:
            start_test_run()
        try:
            test(result)
        finally:
            stop_test_run = getattr(result, "stopTestRun", None)
            if stop_test_run is not None:
                stop_test_run()
    if result.errors or result.failures:
        result.printErrors()
    return result


TextTestRunner.run = _run_without_progress

# Pass is 50. A correct pair below the line is a false rejection.
PASS_PERCENT = 50.0
_AUDIO_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3"}

# idk about genuine and impostor might be wrong
_GENUINE: list[float] = []
_IMPOSTOR: list[float] = []
_CLIPS: list[tuple[str, np.ndarray, int, Clip]] = []
_SCORER = Scorer()
_LOG: io.TextIOWrapper | None = None
_LOG_PATH: Path | None = None
_REVISION = ""


# cant use audio.py because we go to the past git versions and we need consistent sample loading
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


def _audio_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
    )


# FAR and FRR
def _rates(
    genuine: list[float], impostor: list[float], threshold: float
) -> tuple[float, float, int, int]:
    # An incorrect pair on or above the line is a false acceptance.
    false_rejections = sum(score < threshold for score in genuine)
    false_acceptances = sum(score >= threshold for score in impostor)
    false_rejection_rate = 100.0 * false_rejections / len(genuine)
    false_acceptance_rate = 100.0 * false_acceptances / len(impostor)
    return (
        false_acceptance_rate,
        false_rejection_rate,
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


def _log(line: str) -> None:
    if _LOG is not None:
        print(line, file=_LOG)


def _score(
    stem: str, case: str, clip: Clip, samples: np.ndarray, rate: int, correct: bool
) -> None:
    """The percent joins the genuine or impostor list.

    The log states the prediction and the result at 50.
    """
    take = Take(samples=np.asarray(samples), sample_rate=rate, peaks=[])
    percent = _SCORER.percent(clip, take)

    passed = percent >= PASS_PERCENT
    scores = _GENUINE if correct else _IMPOSTOR
    scores.append(percent)
    prediction = "Pass" if correct else "Fail"
    actual = "Pass" if passed else "Fail"

    # pure flat sound / faaah: 10.7 predicted Fail, actual Fail
    _log(f"{case} / {stem}: {percent} predicted {prediction}, actual {actual}")


def _shared(name: str) -> tuple[np.ndarray, int]:
    recordings = ROOT / "tests" / "recordings"
    matches = (
        [path for path in _audio_files(recordings) if path.stem == name]
        if recordings.is_dir()
        else []
    )
    if not matches:
        _log(f"absent {name}")
        raise unittest.SkipTest(f"missing {name}")
    samples, rate = _load_samples(matches[0])
    if samples.size == 0 or rate <= 0:
        raise RuntimeError(f"Could not read audio from {matches[0]}")
    return samples, rate


def _revision_label(commit: str = "HEAD") -> str:
    return subprocess.check_output(
        ["git", "log", "-1", "--format=%h %s", commit], cwd=ROOT, text=True
    ).strip()


def setUpModule() -> None:
    global _LOG, _LOG_PATH, _REVISION
    sounds = ROOT / "sounds"
    if not sounds.is_dir():
        raise RuntimeError(f"Sounds directory does not exist: {sounds}")
    clips = _audio_files(sounds)
    if not clips:
        raise RuntimeError(f"No audio files in {sounds}")
    _LOG_PATH = Path(os.environ.get("BATTERY_LOG", ROOT / "tests" / "battery.log"))
    # The working tree starts the log. Each older revision appends its own trials.
    _LOG = open(
        _LOG_PATH,
        "a" if os.environ.get("BATTERY_APP") else "w",
        encoding="utf-8",
        buffering=1,
    )
    _REVISION = os.environ.get("BATTERY_REVISION") or _revision_label()
    if os.environ.get("BATTERY_APP"):
        _log("")
    _log(f"revision {_REVISION}")
    _GENUINE.clear()
    _IMPOSTOR.clear()
    _CLIPS.clear()
    for path in clips:
        samples, rate = _load_samples(path)
        if samples.size == 0 or rate <= 0:
            raise RuntimeError(f"Could not read audio from {path}")
        duration_ms = max(1, int(round(samples.shape[0] / rate * 1000)))
        clip = Clip(
            samples=samples, sample_rate=rate, duration_ms=duration_ms, peaks=[]
        )
        _CLIPS.append((path.stem, samples, rate, clip))


def tearDownModule() -> None:
    if _GENUINE and _IMPOSTOR:
        false_acceptance_rate, false_rejection_rate, acceptances, rejections = _rates(
            _GENUINE, _IMPOSTOR, PASS_PERCENT
        )
        equal_error_rate, threshold = _eer(_GENUINE, _IMPOSTOR)
        _log("")
        _log(f"genuine={len(_GENUINE)} impostor={len(_IMPOSTOR)}")
        _log(
            f"FAR={false_acceptance_rate:.1f} ({acceptances}/{len(_IMPOSTOR)})"
            f" at {PASS_PERCENT:.0f}"
        )
        _log(
            f"FRR={false_rejection_rate:.1f} ({rejections}/{len(_GENUINE)})"
            f" at {PASS_PERCENT:.0f}"
        )
        _log(f"EER={equal_error_rate:.1f} at {threshold:.1f}")
        print(
            f"{_REVISION} FAR={false_acceptance_rate:.1f}"
            f" FRR={false_rejection_rate:.1f} EER={equal_error_rate:.1f}",
            flush=True,
        )
    if _LOG is not None:
        _LOG.close()
    # This process was started for one older revision. The parent walks the rest.
    if os.environ.get("BATTERY_APP") or _LOG_PATH is None:
        return
    commits = subprocess.check_output(
        ["git", "log", "--reverse", "--format=%H", "--", "app/score.py"],
        cwd=ROOT,
        text=True,
    ).split()
    for commit in commits:
        with tempfile.TemporaryDirectory(prefix="battery-") as temporary:
            app_dir = Path(temporary) / "app"
            app_dir.mkdir()
            # Regular package, so the import uses this revision's files.
            (app_dir / "__init__.py").write_text("", encoding="utf-8")
            for name in ("score.py", "audio.py"):
                source = subprocess.check_output(
                    ["git", "show", f"{commit}:app/{name}"], cwd=ROOT
                )
                (app_dir / name).write_bytes(source)
            env = os.environ.copy()
            env["BATTERY_APP"] = temporary
            env["BATTERY_REVISION"] = _revision_label(commit)
            env["BATTERY_LOG"] = str(_LOG_PATH)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            subprocess.run(
                [sys.executable, "-m", "unittest", "tests.test_rates"],
                cwd=ROOT,
                env=env,
                check=True,
            )


class ImitationTest(unittest.TestCase):
    def test_nothing(self) -> None:
        for stem, samples, rate, clip in _CLIPS:
            _score(stem, "nothing", clip, np.zeros_like(samples), rate, False)

    def test_same_sound(self) -> None:
        for stem, samples, rate, clip in _CLIPS:
            _score(stem, "the same sound", clip, samples, rate, True)

    def test_plausible(self) -> None:
        found = False
        recordings = ROOT / "tests" / "recordings"
        for stem, _, _, clip in _CLIPS:
            folder = recordings / stem / "plausible"
            files = _audio_files(folder) if folder.is_dir() else []
            if not files:
                _log(f"absent {stem}/plausible")
                continue
            for recording in files:
                found = True
                recorded, recorded_rate = _load_samples(recording)
                if recorded.size == 0 or recorded_rate <= 0:
                    raise RuntimeError(f"Could not read audio from {recording}")
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

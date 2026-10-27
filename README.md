# Sound imitation

When you die in Minecraft, the game locks the keyboard and mouse, plays a random clip, and records you imitating it. The round repeats that same clip until the score clears the threshold, or until you press the panic shortcut.

The page at `http://127.0.0.1:8765` is meant for an OBS browser source. It draws the reference waveform, the live recording, the countdown, the attempt number, and the pass or fail result. The page background is transparent.

This runs on Windows. The input lock uses low-level keyboard and mouse hooks, and the default Minecraft log path is under `%APPDATA%`.

## Setup

Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

Put clips in `sounds/`. Accepted types are `.wav`, `.flac`, `.ogg`, and `.mp3`. The first run writes `config.json` if it is missing, then stops so you can set `player_name`.

```bash
python main.py
```

Add the overlay URL as a browser source in OBS. The port is `overlay_port` in `config.json` (8765 by default).

## Commands

| Command | What it does |
| --- | --- |
| `python main.py` | Tail `latest.log` and start a locked round on your death. |
| `python main.py --demo` | Play one random clip, count down, record, and score. Input stays unlocked. |
| `python main.py --listen` | Print each chat line as `death` or `ignore`. |
| `python main.py --lock-test` | Lock input for 5 seconds, or until the panic shortcut. |

Only one of `--listen`, `--demo`, and `--lock-test` can be set.

## A round

1. A death line for `player_name` shows up in the Minecraft log.
2. Keyboard and mouse input is swallowed.
3. A random clip plays, with its quiet lead-in cut off.
4. A countdown beeps once per second. Each beep is a short built-in tone, or the first 0.3 seconds of `countdown_sound` when that path is set.
5. The microphone records for the length of the clip.
6. The score is a time-aligned spectral similarity, printed as a percentage. A take that is mostly noise scores 0.
7. At or above `threshold_percent`, the lock releases. Below it, the same clip plays again.

Deaths already in the log when the program starts are skipped. Chat written during a round is skipped when the round ends, so one death does not start a second round.

Press `panic_shortcut` (default `ctrl+alt+f12`) to abort the round and restore input. `--listen` does not lock input.

## Score log

The pass line is `threshold_percent`, default 70. The percentage is the mean similarity of frames along a time warp. Each entry is the commit that put that comparison in `app/score.py`, the check that was run, and why it stayed or was thrown out. `6ea0134` ("license") only added the license lines and is not a scoring change.

### `f537911` — failed

2026-10-17, "pre refactor". This commit adds `app/score.py`. Each clip and each take is an amplitude envelope, aligned with dynamic time warping over 20% of the longer envelope, then scored with Pearson correlation.

Tested by tapping along with a rhythmic clip. The taps cleared the pass line. A tap train has the same loudness shape as the clip, so the warp treated tapping the desk as an imitation.

### `8d71c34` — failed

2026-10-17, "up". Replaces the envelope with eight log-spaced band energies from 80 Hz to 7.6 kHz. Each frame is divided so the bands sum to 1, and frames are compared with cosine similarity. The warp stays at 20% of the longer clip.

This stopped the taps. A tap fills every band, and a voice or a tone keeps its energy in a few. It failed a breath. A breath also covers every band, and cosine still counted that as a match against a clip that uses only some of the bands. That is the reason recorded in the next commit.

### `38b4d9a` — failed

2026-10-17, "breath fix". Replaces cosine with histogram intersection, and narrows the warp from 20% of the clip to 80 ms, so a small slip still matches and a late start does not.

Tested on real microphone takes against the clips. Scores landed about 25–57, under the pass line. On two histograms with the same bin sum, intersection is half an L1 distance, so noise in bands the clip leaves empty took about half the score away from a real imitation.

### `1028b2d` — held

2026-10-17, "fix breath". This is the scorer that is in the tree now. The same eight bands, converted with `20 log10` and with the frame mean subtracted, compared again with cosine. The 80 ms warp stays. A take whose median spectral flatness is above 0.45 scores 0.

Tested in `Scorer` on the four clips in `sounds/`:

- Each clip against itself, and against the same samples at 0.15 gain: both near 100. An exact copy is 100 because the cosine of a vector with itself is 1. A gain is a constant in decibels, so subtracting the frame mean keeps the quiet copy on that same vector.
- Each clip against broadband noise of the same length: under 70.
- A pure tone against that noise: under 70.

Cosine alone still passed a clipped breath, at 79% against the Spongebob clip. Cosine only sees which bands are strong relative to each other, and that breath pointed the same way. Its flatness (geometric mean of the eight bands divided by their arithmetic mean) was 0.55–0.64. Every reference clip is at most 0.20. The 0.45 gate sits between those two measurements, so that breath scores 0. Flatness only rejects the take. The percentage is still the cosine.

### Not run

No commit. These were read and left out.

- A codebook histogram, and a spectral-flatness fingerprint. Both compare an unordered collection of frames and answer which recording a library contains. This score has to follow one short clip in time.
- MFCCs. The eight log bands were already the feature that held the copy, quiet-copy, and noise checks. The warp still compares those bands.

## Config

`config.json` sits next to `main.py`.

| Key | Meaning |
| --- | --- |
| `player_name` | Minecraft name. Death lines must start with this name. |
| `log_path` | Path to `latest.log`. |
| `sounds_dir` | Folder of reference clips. Relative paths are resolved from the config file. |
| `countdown_sound` | Clip used for each countdown tick, or `null` for the built-in beep. |
| `threshold_percent` | Minimum score that ends the round. Default 70. |
| `countdown_seconds` | Seconds to count down before recording. At least 1. |
| `overlay_port` | Local port for the overlay page and its websocket. |
| `panic_shortcut` | Keys that release the lock, joined with `+`. Modifiers are `ctrl`, `alt`, and `shift`. The last part is a letter, `f1`–`f12`, or `esc`, `escape`, `pause`, `end`, `space`, `tab`, `backspace`. |
| `extra_patterns` | Extra regular expressions. A chat line that matches any of them is also a death. Advancement lines are never deaths. |

The built-in matcher covers vanilla English death messages, including item variants such as `using Diamond Sword`.

## License

Copyright (C) 2026 drak-o

Sound imitation is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

The license text is in [LICENSE](LICENSE).

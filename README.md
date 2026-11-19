# Sound imitation

When you die in Minecraft, the game locks the keyboard and mouse, plays a random clip, and records you imitating it. The round repeats that same clip until the score clears the threshold, or until you press the panic shortcut.

The page at `http://127.0.0.1:8765` is meant for an OBS browser source. It draws the reference waveform, the live recording, the countdown, the attempt number, and the pass or fail result. The page background is transparent.

This runs on Windows. The input lock uses pynput, and the default Minecraft log path is under `%APPDATA%`.

## Setup

Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

Put clips in `sounds/`. Accepted types are `.wav`, `.flac`, `.ogg`, and `.mp3`. `config.json` ships next to `main.py`. Set `player_name` before running.

```bash
python main.py
```

Add the overlay URL as a browser source in OBS. The port is `overlay_port` in `config.json` (8765 by default).

## Commands

| Command          | What it does                                              |
| ---------------- | --------------------------------------------------------- |
| `python main.py` | Tail `latest.log` and start a locked round on your death. |

## A round

1. A death line for `player_name` shows up in the Minecraft log.
2. Keyboard and mouse input is swallowed.
3. A random clip plays, with its quiet lead-in cut off.
4. A countdown beeps once per second. Each beep is a short built-in tone, or the first 0.3 seconds of `countdown_sound` when that path is set.
5. The microphone records for the length of the clip.
6. The score is the mean of the per-frame loudness ratios, as a percentage. Both sounds are resampled to 16 kHz. Each frame is the mean absolute level over 10 ms, and where either frame is audible the ratio is the quieter level divided by the louder one. The overlay shows the percentage with the pass or fail result.
7. At or above `threshold_percent`, the lock releases. Below it, the same clip plays again.

Deaths already in the log when the program starts are skipped. Chat written during a round is skipped when the round ends, so one death does not start a second round.

Press `panic_shortcut` (default `<ctrl>+<alt>+<f12>`) to abort the round and restore input.

## Testing

The imitation battery is `tests/test_rates.py`. It scores every clip in `sounds/` and writes each result to `tests/battery.log`. Unittest's own progress stays on the console.

```bash
python -m unittest tests.test_rates
```

Pass inside the test is 50. That line is fixed in the test file. It does not read `threshold_percent`.

Eight cases. A genuine pair is expected to pass: the clip against itself, the same clip with a little hiss, and a microphone take in `tests/recordings/` whose file name matches the clip. An impostor is expected to fail: a microphone recording of nothing, a 440 Hz tone, the same clip started 200 ms late, and the shared `breathing` and `tapping` recordings scored against every clip. A missing `nothing`, `breathing`, or `tapping` file skips that case. If no recording shares a clip's name, the plausible case is skipped.

Before scoring, the take is cut or padded with silence to the clip's length, so each 10 ms frame lines up. The end of `tests/battery.log` reports how many genuine pairs were rejected, how many impostors were accepted, and the threshold where those two rates are closest.

## Config

`config.json` sits next to `main.py`.

| Key                 | Meaning                                                                                                                                                                                                    |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `player_name`       | Minecraft name. Death lines must start with this name.                                                                                                                                                     |
| `log_path`          | Path to `latest.log`.                                                                                                                                                                                      |
| `sounds_dir`        | Folder of reference clips. Relative paths are resolved from the config file.                                                                                                                               |
| `countdown_sound`   | Clip used for each countdown tick, or `null` for the built-in beep.                                                                                                                                        |
| `threshold_percent` | Minimum score that ends the round. Default 50.                                                                                                                                                             |
| `countdown_seconds` | Seconds to count down before recording. At least 1.                                                                                                                                                        |
| `overlay_port`      | Local port for the overlay page and its websocket.                                                                                                                                                         |
| `panic_shortcut`    | pynput hotkey that releases the lock. A special key is wrapped in brackets (`<ctrl>+<alt>+<f12>`, `<esc>`). A character is written as itself. `<ctrl>`, `<alt>`, `<shift>`, and `<cmd>` match either side. |

The built-in matcher covers vanilla English death messages, including item variants such as `using Diamond Sword`.

## License

Copyright (C) 2026 drak-o

Sound imitation is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

The license text is in [LICENSE](LICENSE).

# study approach

the same approach you used for bompa is used here:

- generate podcast text.
- TTS using piper.
- Listen to podcast. (exposure, scope)
- Read + take notes + flashcards. (retention)

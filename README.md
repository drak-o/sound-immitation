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

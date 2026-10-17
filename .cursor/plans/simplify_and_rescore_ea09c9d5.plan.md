---
name: Simplify and rescore
overview: Remove device selection and one-use helpers, rename the panic setting, score short-time spectra so taps cannot pass, and replace the Next.js rules with rules that match this Python app. Existing config keys are not read as fallbacks.
todos:
  - id: rules
    content: Delete Next.js rules, rewrite coding conventions, add the inline-single-use rule, and trim the philosophy examples.
    status: completed
  - id: config-devices
    content: Drop device keys and legacy names, rename panic_shortcut, pass sounds_dir into AudioSession, delete list-devices and app/__init__.py.
    status: completed
  - id: inline
    content: Inline one-use helpers in chat_watch and audio, share one commented overlay column count, and run Black.
    status: completed
  - id: spectra
    content: Score 8-band frame spectra with cosine DTW so taps no longer match a tonal clip.
    status: completed
isProject: false
---

# Simplify modules and stop tap-scoring

No legacy config. [config.json](config.json) is rewritten to the new keys. `panic_chord`, `input_device`, and `output_device` are not read. A file that still has only the old names gets the new defaults.

## Rules

Delete the Next.js rules: [cms-conventions.mdc](.cursor/rules/cms-conventions.mdc), [server-api.mdc](.cursor/rules/server-api.mdc), [modal-structure.mdc](.cursor/rules/modal-structure.mdc), [pen-design.mdc](.cursor/rules/pen-design.mdc), [component-structure.mdc](.cursor/rules/component-structure.mdc), [ui-primitives-first.mdc](.cursor/rules/ui-primitives-first.mdc), [mobile-first.mdc](.cursor/rules/mobile-first.mdc).

Keep [no-markdown-files.mdc](.cursor/rules/no-markdown-files.mdc) and [preserve-user-refactors.mdc](.cursor/rules/preserve-user-refactors.mdc).

Rewrite [coding-conventions.mdc](.cursor/rules/coding-conventions.mdc) for this app: English names, format Python with Black (default 88), no Next.js or locale rules.

Add [.cursor/rules/inline-single-use.mdc](.cursor/rules/inline-single-use.mdc), always on: a function used once in the same file is inlined, and the block gets a comment saying what the number or step is for. A one-line wrapper is always inlined. A real algorithm that is called once (band spectra, DTW, shortcut key parsing) stays named.

Trim [philosophy-of-software-design.mdc](.cursor/rules/philosophy-of-software-design.mdc) to the deep-module rules and one Python example. Remove the Next.js export examples.

## Config and devices

In [app/config.py](app/config.py), fold `default_log_path`, `_resolve`, and `_optional_path` into `Config.load`. Delete `_optional_name`.

`Config` keeps `player_name`, `log_path`, `sounds_dir`, `countdown_sound`, `threshold_percent`, `countdown_seconds`, `overlay_port`, `panic_shortcut`, `extra_patterns`. Playback and recording always use the Windows default devices (`device=None` in sounddevice). Delete `--list-devices` from [main.py](main.py).

[app/audio.py](app/audio.py) `AudioSession` is constructed with `sounds_dir` and `countdown_sound` only. `pick_random()` takes no directory. [app/round.py](app/round.py) calls `pick_random()` with no argument.

Rename `panic_chord` to `panic_shortcut` in [app/input_lock.py](app/input_lock.py), [app/round.py](app/round.py), and [main.py](main.py). Error text says `panic_shortcut`. The VK parser stays; it is the shortcut grammar, not a wrapper.

Delete empty [app/**init**.py](app/__init__.py).

## Inline the one-use helpers

[app/chat_watch.py](app/chat_watch.py): `next_chat` owns the poll, the rotation check, and the line split, in the shape you wrote. `extract_chat` stays. Startup and `drain` still seek to the end of the file so old deaths are not replayed, and a missing log still prints once. The file is still opened and closed every read so Minecraft can rename `latest.log`.

[app/audio.py](app/audio.py):

- Delete `_find_device`, `_device_rate`, `list_devices`, and the `play` wrapper. `countdown` calls the same playback loop through `play`.
- Inline the synthesized tick into init. Comment that the beep is 40 ms at 48 kHz and is only used when `countdown_sound` is null.
- Inline `_wait` into `countdown`.
- Type `abort` as `threading.Event` and call `is_set` directly. Delete `_aborted`.
- One constant for the overlay, with a comment that it is the number of horizontal buckets drawn on the waveform, not a sample rate and not a sample count:

```python
# Horizontal buckets on the overlay waveform. Not samples, and not samples per second.
OVERLAY_COLUMN_COUNT = 400
```

[app/round.py](app/round.py) imports that constant. The local `_COLUMNS = 400` goes away.

Comments on the other audio numbers: `0.05` seconds of audio per read or write (abort is checked 20 times a second); the countdown beep is cut at `0.3` seconds so it finishes inside the one-second gap.

`resample` and `waveform_columns` stay. Each is used more than once.

Run Black on the Python files so the long `if` lines in device matching are gone with the functions, and the rest of the package uses one width.

## Score spectra, not loudness

Taps cheat the current scorer because [app/score.py](app/score.py) compares amplitude envelopes. A tap train has the same loudness shape as a rhythmic clip. Replace `_envelope` with short-time spectra.

- Resample to 16 kHz. Frames stay 25 ms with a 10 ms hop.
- Each frame becomes 8 log-spaced band energies from about 80 Hz to 7.6 kHz. The bands in a frame are divided by their sum, so overall loudness cannot create a match. A tap puts energy in every band. A voice or a tone keeps it in a few.
- Drop quiet edge frames on the take only, using total frame energy.
- DTW still aligns time, with a 20% band. The local cost is the cosine distance between those 8-band frames, not `abs` of two loudness numbers.
- The percentage is the mean cosine similarity along the warp path, times 100, clamped at 0. Print that similarity next to the percentage.
- Delete the flat-envelope shortcut in `_pearson`. Two signals that are both steady in time can still fail when their bands differ.

A click train against a narrow tone should land well under the default 70. Re-test with taps on `sounds/faaah.mp3` after the change; the threshold stays in config.

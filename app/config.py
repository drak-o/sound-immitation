"""Load the local config file, or write defaults and stop."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def _defaults() -> dict:
    appdata = os.environ.get("APPDATA")
    if appdata:
        log_path = Path(appdata) / ".minecraft" / "logs" / "latest.log"
    else:
        log_path = (
            Path.home() / "AppData" / "Roaming" / ".minecraft" / "logs" / "latest.log"
        )
    return {
        "player_name": "",
        "log_path": str(log_path),
        "sounds_dir": "sounds",
        "countdown_sound": None,
        "threshold_percent": 70,
        "countdown_seconds": 3,
        "overlay_port": 8765,
        "panic_shortcut": "ctrl+alt+f12",
        "extra_patterns": [],
    }


@dataclass(frozen=True)
class Config:
    player_name: str
    log_path: Path
    sounds_dir: Path
    countdown_sound: Path | None
    threshold_percent: float
    countdown_seconds: int
    overlay_port: int
    panic_shortcut: str
    extra_patterns: tuple[str, ...]

    @staticmethod
    def load(path: Path | None = None) -> Config:
        config_path = path or CONFIG_PATH
        if not config_path.exists():
            config_path.parent.joinpath("sounds").mkdir(exist_ok=True)
            config_path.write_text(
                json.dumps(_defaults(), indent=2) + "\n", encoding="utf-8"
            )
            raise SystemExit(
                f"Wrote {config_path.name}. Set player_name, then run again."
            )

        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"{config_path.name} is not valid JSON: {error}"
            ) from error
        if not isinstance(raw, dict):
            raise SystemExit(f"{config_path.name} must contain an object.")

        # Old names such as panic_chord and the device keys are not read.
        merged = {**_defaults(), **raw}
        base = config_path.parent

        def resolve(value: str) -> Path:
            candidate = Path(value)
            if candidate.is_absolute():
                return candidate
            return (base / candidate).resolve()

        patterns = merged["extra_patterns"]
        if not isinstance(patterns, list) or not all(
            isinstance(item, str) for item in patterns
        ):
            raise SystemExit("extra_patterns must be a list of strings.")

        player_name = merged["player_name"]
        if not isinstance(player_name, str):
            raise SystemExit("player_name must be a string.")

        panic_shortcut = merged["panic_shortcut"]
        if not isinstance(panic_shortcut, str) or not panic_shortcut.strip():
            raise SystemExit("panic_shortcut must be a non-empty string.")

        try:
            threshold = float(merged["threshold_percent"])
            countdown_seconds = int(merged["countdown_seconds"])
            overlay_port = int(merged["overlay_port"])
        except (TypeError, ValueError) as error:
            raise SystemExit(
                "threshold_percent, countdown_seconds, and overlay_port must be numbers."
            ) from error
        if countdown_seconds < 1:
            raise SystemExit("countdown_seconds must be at least 1.")
        if not 0 < overlay_port < 65536:
            raise SystemExit("overlay_port must be a TCP port.")

        log_path = merged["log_path"]
        sounds_dir = merged["sounds_dir"]
        if not isinstance(log_path, str) or not isinstance(sounds_dir, str):
            raise SystemExit("log_path and sounds_dir must be paths.")

        countdown_sound = merged["countdown_sound"]
        if countdown_sound is None or countdown_sound == "":
            resolved_countdown = None
        elif not isinstance(countdown_sound, str):
            raise SystemExit("countdown_sound must be a path or null.")
        else:
            resolved_countdown = resolve(countdown_sound)

        return Config(
            player_name=player_name.strip(),
            log_path=resolve(log_path),
            sounds_dir=resolve(sounds_dir),
            countdown_sound=resolved_countdown,
            threshold_percent=threshold,
            countdown_seconds=countdown_seconds,
            overlay_port=overlay_port,
            panic_shortcut=panic_shortcut.strip().lower(),
            extra_patterns=tuple(patterns),
        )

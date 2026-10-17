"""Load the local config file, or write defaults and stop."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def default_log_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / ".minecraft" / "logs" / "latest.log"
    return Path.home() / "AppData" / "Roaming" / ".minecraft" / "logs" / "latest.log"


def _defaults() -> dict:
    return {
        "player_name": "",
        "log_path": str(default_log_path()),
        "sounds_dir": "sounds",
        "countdown_sound": None,
        "threshold_percent": 70,
        "countdown_seconds": 3,
        "overlay_port": 8765,
        "input_device": None,
        "output_device": None,
        "panic_chord": "ctrl+alt+f12",
        "extra_patterns": [],
    }


def _resolve(value: str, base: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _optional_path(value, base: Path) -> Path | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SystemExit("countdown_sound must be a path or null.")
    return _resolve(value, base)


def _optional_name(value, label: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SystemExit(f"{label} must be a device name or null.")
    return value


@dataclass(frozen=True)
class Config:
    player_name: str
    log_path: Path
    sounds_dir: Path
    countdown_sound: Path | None
    threshold_percent: float
    countdown_seconds: int
    overlay_port: int
    input_device: str | None
    output_device: str | None
    panic_chord: str
    extra_patterns: tuple[str, ...]

    @staticmethod
    def load(path: Path | None = None) -> Config:
        config_path = path or CONFIG_PATH
        if not config_path.exists():
            config_path.parent.joinpath("sounds").mkdir(exist_ok=True)
            config_path.write_text(json.dumps(_defaults(), indent=2) + "\n", encoding="utf-8")
            raise SystemExit(f"Wrote {config_path.name}. Set player_name, then run again.")

        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SystemExit(f"{config_path.name} is not valid JSON: {error}") from error
        if not isinstance(raw, dict):
            raise SystemExit(f"{config_path.name} must contain an object.")

        merged = {**_defaults(), **raw}
        base = config_path.parent
        patterns = merged["extra_patterns"]
        if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
            raise SystemExit("extra_patterns must be a list of strings.")

        player_name = merged["player_name"]
        if not isinstance(player_name, str):
            raise SystemExit("player_name must be a string.")

        panic_chord = merged["panic_chord"]
        if not isinstance(panic_chord, str) or not panic_chord.strip():
            raise SystemExit("panic_chord must be a non-empty string.")

        try:
            threshold = float(merged["threshold_percent"])
            countdown_seconds = int(merged["countdown_seconds"])
            overlay_port = int(merged["overlay_port"])
        except (TypeError, ValueError) as error:
            raise SystemExit("threshold_percent, countdown_seconds, and overlay_port must be numbers.") from error
        if countdown_seconds < 1:
            raise SystemExit("countdown_seconds must be at least 1.")
        if not 0 < overlay_port < 65536:
            raise SystemExit("overlay_port must be a TCP port.")

        log_path = merged["log_path"]
        sounds_dir = merged["sounds_dir"]
        if not isinstance(log_path, str) or not isinstance(sounds_dir, str):
            raise SystemExit("log_path and sounds_dir must be paths.")

        return Config(
            player_name=player_name.strip(),
            log_path=_resolve(log_path, base),
            sounds_dir=_resolve(sounds_dir, base),
            countdown_sound=_optional_path(merged["countdown_sound"], base),
            threshold_percent=threshold,
            countdown_seconds=countdown_seconds,
            overlay_port=overlay_port,
            input_device=_optional_name(merged["input_device"], "input_device"),
            output_device=_optional_name(merged["output_device"], "output_device"),
            panic_chord=panic_chord.strip().lower(),
            extra_patterns=tuple(patterns),
        )

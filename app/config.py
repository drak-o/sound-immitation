"""Load the local config file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

# resolve the path of the value relative to the root
def _resolve(value: str) -> Path:
    candidate = Path(os.path.expandvars(value))
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


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

    @staticmethod
    def load(path: Path | None = None) -> Config:
        config_path = path or CONFIG_PATH
        if not config_path.exists():
            raise SystemExit(f"{config_path.name} is missing.")

        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))

            threshold = float(raw["threshold_percent"])
            countdown_seconds = int(raw["countdown_seconds"])
            overlay_port = int(raw["overlay_port"])
            if countdown_seconds < 1:
                raise SystemExit("countdown_seconds must be at least 1.")
            if not 0 < overlay_port < 65536:
                raise SystemExit("overlay_port must be a TCP port.")

            countdown_sound = raw["countdown_sound"]
            if countdown_sound is None or countdown_sound == "":
                resolved_countdown = None
            else:
                resolved_countdown = _resolve(countdown_sound)

            return Config(
                player_name=raw["player_name"].strip(),
                log_path=_resolve(raw["log_path"]),
                sounds_dir=_resolve(raw["sounds_dir"]),
                countdown_sound=resolved_countdown,
                threshold_percent=threshold,
                countdown_seconds=countdown_seconds,
                overlay_port=overlay_port,
                panic_shortcut=raw["panic_shortcut"],
            )
        except (
            TypeError,
            ValueError,
            AttributeError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            raise SystemExit(f"{config_path.name}: {error}") from error

"""Minecraft death sound challenge."""

from __future__ import annotations

from app.chat import ChatWatch, DeathMatcher
from app.config import Config


class App:
    def __init__(self) -> None:
        self._hub = None

    def run(self) -> None:
        self._watch(Config.load())

    def _watch(self, config: Config) -> None:
        self._require_player(config)
        print(f"Overlay at http://127.0.0.1:{config.overlay_port}")
        controller = self._controller(config)
        watch = ChatWatch(config.log_path)
        matcher = DeathMatcher(config.player_name)
        print(f"Waiting for {config.player_name} in {config.log_path}")
        while True:
            text = watch.wait_for_death(matcher)
            print(f"death: {text}")
            controller.run_locked()
            watch.drain()

    def _controller(self, config: Config):
        from app.audio import AudioSession
        from app.input_lock import InputLock
        from app.overlay_server import OverlayHub
        from app.round import RoundController
        from app.score import Scorer

        audio = AudioSession(config.sounds_dir, config.countdown_sound)
        hub = OverlayHub()
        self._hub = hub
        hub.start(config.overlay_port)
        return RoundController(config, audio, Scorer(), hub, InputLock())

    @staticmethod
    def _require_player(config: Config) -> None:
        if not config.player_name:
            raise SystemExit("Set player_name in config.json.")


def main() -> None:
    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if app._hub is not None:
            app._hub.stop()


if __name__ == "__main__":
    main()

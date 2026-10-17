"""Minecraft death sound challenge."""

from __future__ import annotations

import argparse
import sys
import threading
import time

from app.chat_watch import ChatWatch
from app.config import ROOT, Config
from app.deaths import DeathMatcher


class App:
    def __init__(self) -> None:
        self._hub = None

    def run(self) -> None:
        parser = argparse.ArgumentParser(
            description="Play a sound when you die in Minecraft and record an imitation."
        )
        parser.add_argument(
            "--listen", action="store_true", help="Print chat lines as death or ignore."
        )
        parser.add_argument(
            "--demo",
            action="store_true",
            help="Play one random clip, count down, record, and score.",
        )
        parser.add_argument(
            "--lock-test",
            action="store_true",
            help="Lock input for 5 seconds, or until the panic shortcut.",
        )
        args = parser.parse_args()
        selected = sum(bool(flag) for flag in (args.listen, args.demo, args.lock_test))
        if selected > 1:
            parser.error("Choose only one of --listen, --demo, or --lock-test.")

        config = Config.load()
        if args.lock_test:
            self._lock_test(config)
            return
        if args.listen:
            self._listen(config)
            return
        if args.demo:
            self._demo(config)
            return
        self._watch(config)

    def _listen(self, config: Config) -> None:
        self._require_player(config)
        print(f"Listening to {config.log_path}")
        watch = ChatWatch(config.log_path)
        matcher = DeathMatcher(config.player_name, config.extra_patterns)
        while True:
            text = watch.next_chat()
            kind = "death" if matcher.matches(text) else "ignore"
            print(f"{kind}: {text}")

    def _demo(self, config: Config) -> None:
        controller = self._controller(config)
        print(f"Overlay at http://127.0.0.1:{config.overlay_port}")
        controller.run_demo()

    def _watch(self, config: Config) -> None:
        self._require_player(config)
        print(f"Overlay at http://127.0.0.1:{config.overlay_port}")
        controller = self._controller(config)
        watch = ChatWatch(config.log_path)
        matcher = DeathMatcher(config.player_name, config.extra_patterns)
        print(f"Waiting for {config.player_name} in {config.log_path}")
        while True:
            text = watch.wait_for_death(matcher)
            print(f"death: {text}")
            controller.run_locked()
            watch.drain()

    def _lock_test(self, config: Config) -> None:
        from app.input_lock import InputLock

        lock = InputLock()
        abort = threading.Event()
        print(
            f"Input locked for 5 seconds. Press {config.panic_shortcut} to release sooner."
        )
        lock.start(config.panic_shortcut, abort.set)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not abort.is_set():
                time.sleep(0.05)
        finally:
            lock.stop()
        print("Input restored.")

    def _controller(self, config: Config):
        from app.audio import AudioSession
        from app.input_lock import InputLock
        from app.overlay_server import OverlayHub
        from app.round import RoundController
        from app.score import Scorer

        audio = AudioSession(config.sounds_dir, config.countdown_sound)
        hub = OverlayHub(ROOT / "overlay")
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

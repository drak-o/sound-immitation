"""Vanilla English death lines for one player name."""

from __future__ import annotations

import re

# Remainder after "<player> ". Matched with startswith so item variants
# ("using Diamond Sword") still count.
SUFFIXES = (
    "was shot by",
    "was pummeled by",
    "was pricked to death",
    "walked into a cactus",
    "drowned",
    "experienced kinetic energy",
    "removed an elytra while flying",
    "blew up",
    "was blown up by",
    "was killed by",
    "was killed trying to hurt",
    "hit the ground too hard",
    "fell from a high place",
    "fell off",
    "fell while climbing",
    "fell out of the world",
    "fell too far",
    "was doomed to fall",
    "was impaled",
    "was squashed by",
    "was squished too much",
    "went up in flames",
    "burned to death",
    "was burnt to a crisp",
    "walked into fire",
    "went off with a bang",
    "tried to swim in lava",
    "was struck by lightning",
    "discovered the floor was lava",
    "walked into danger zone",
    "froze to death",
    "was frozen to death",
    "was slain by",
    "was fireballed by",
    "was stung to death",
    "was poked to death",
    "withered away",
    "suffocated in a wall",
    "was roasted in dragon breath",
    "died",
    "was skewered by",
    "was smashed by",
    "was obliterated by a sonically-charged shriek",
    "didn't want to live in the same world",
)

_ADVANCEMENT_PHRASES = (
    "has made the advancement",
    "has completed the challenge",
    "has reached the goal",
)


class DeathMatcher:
    def __init__(self, player_name: str, extra_patterns: tuple[str, ...] = ()) -> None:
        self._player = player_name
        try:
            self._extra = tuple(re.compile(pattern) for pattern in extra_patterns)
        except re.error as error:
            raise SystemExit(f"Invalid extra_patterns regex: {error}") from error

    def matches(self, chat_text: str) -> bool:
        if any(phrase in chat_text for phrase in _ADVANCEMENT_PHRASES):
            return False
        if self._player and chat_text.startswith(self._player + " "):
            remainder = chat_text[len(self._player) + 1 :]
            if any(remainder.startswith(suffix) for suffix in SUFFIXES):
                return True
        return any(pattern.search(chat_text) for pattern in self._extra)

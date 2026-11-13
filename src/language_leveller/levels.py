"""Level scale. CEFR by default; a language config may supply its own ordered scale."""

from __future__ import annotations

DEFAULT_SCALE = ["A1", "A2", "B1", "B2", "C1", "C2", "C2+"]


class Scale:
    def __init__(self, levels: list[str] | None = None):
        self.levels = list(levels or DEFAULT_SCALE)
        self._idx = {lv: n for n, lv in enumerate(self.levels)}

    def index(self, level: str) -> int:
        try:
            return self._idx[level]
        except KeyError:
            raise ValueError(f"Unknown level {level!r}; scale is {self.levels}") from None

    def max(self, levels) -> str | None:
        levels = [lv for lv in levels if lv]
        return max(levels, key=self.index) if levels else None

    def __contains__(self, level: str) -> bool:
        return level in self._idx

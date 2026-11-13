"""Backend-neutral data model: every parser backend produces these objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Token:
    i: int                      # index within the sentence (0-based)
    text: str
    lemma: str
    upos: str                   # Universal POS tag (VERB, NOUN, ADP, ...)
    feats: dict[str, str]       # UD morphological features, e.g. {"Mood": "Sub"}
    head: int                   # index of head token; == i for the root
    rel: str                    # UD dependency relation (may carry a subtype, e.g. "aux:pass")
    start: int = 0              # char offsets in the cleaned sentence text
    end: int = 0

    @property
    def lower(self) -> str:
        return self.text.lower()

    def feat_values(self, key: str) -> set[str]:
        """UD allows multi-valued features ("PronType=Int,Rel")."""
        v = self.feats.get(key)
        return set(v.split(",")) if v else set()


@dataclass
class Sentence:
    text: str
    tokens: list[Token] = field(default_factory=list)

    def children(self, i: int) -> list[Token]:
        return [t for t in self.tokens if t.head == i and t.i != i]


@dataclass
class Segment:
    """A piece of source text heading for the parser, with what the cleaner removed."""
    original: str
    clean: str
    start: int                  # char offset of `original` in the source text
    end: int
    ignored: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    parsed: Optional[list[Sentence]] = None

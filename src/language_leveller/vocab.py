"""Frequency vocabulary list: loading, lemma lookup and rank -> level banding.

File format (TSV or CSV, header row required; see docs/FORMATS.md):
  rank  word  pos  gloss  [level]  [variants]  [translit]
`variants` holds inflected/alternative forms separated by `|`.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .levels import Scale
from .model import Sentence, Token

REQUIRED = ("rank", "word", "pos")


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).lower().strip()


def fold(s: str) -> str:
    """Strip diacritics (for unaccented internet spellings)."""
    d = unicodedata.normalize("NFD", s)
    return unicodedata.normalize("NFC", "".join(c for c in d if not unicodedata.combining(c)))


def parse_tags(s: str) -> dict:
    """'region=CL,AR; register=colloquial' -> {'region': ['CL','AR'], 'register': ['colloquial']}"""
    out: dict[str, list[str]] = {}
    for part in s.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out.setdefault(k.strip(), []).extend(x.strip() for x in v.split(",") if x.strip())
    return out


@dataclass
class Entry:
    rank: int
    word: str
    pos: str
    gloss: str = ""
    level: str = ""
    variants: list[str] = field(default_factory=list)
    translit: str = ""
    id: str = ""
    feats: str = ""                 # learner-relevant facts, UD syntax (Gender=Fem)
    tags: dict = field(default_factory=dict)   # e.g. {"region": ["CL", "AR"], "register": ["colloquial"]}
    fixed_level: bool = False       # level came from the file, not from bands

    @property
    def regions(self) -> list[str]:
        return self.tags.get("region", [])


@dataclass
class Lookup:
    entry: Entry | None
    method: str            # lemma | variant | form | clitic | folded | none
    candidates: int = 0


class Vocab:
    def __init__(self, entries: list[Entry], config: dict, scale: Scale):
        self.entries = sorted(entries, key=lambda e: e.rank)
        self.cfg = config
        self.scale = scale
        self.size = max((e.rank for e in entries), default=0)
        self.set_bands(config.get("bands", []), _recompute=False)
        self.unranked_level = config.get("unranked_level", scale.levels[-1])
        # language POS codes in the list -> set of UPOS tags they are compatible with
        self.pos_map = {k: set(v if isinstance(v, list) else [v])
                        for k, v in config.get("pos_map", {}).items()}
        self.exclude_upos = set(config.get("exclude_upos", ["PUNCT", "SYM", "PROPN", "SPACE"]))
        self.clitic_patterns = [re.compile(p) for p in config.get("clitic_suffixes", [])]
        self.accent_fallback = config.get("accent_fold_fallback", True)
        self.exclude_patterns = [re.compile(p) for p in config.get("exclude_patterns", [])]
        self.morph = None   # optional MorphLexicon, attached by the Leveller

        self.by_lemma: dict[str, list[Entry]] = {}
        self.by_form: dict[str, list[Entry]] = {}
        self.by_fold: dict[str, list[Entry]] = {}
        for e in self.entries:
            self.by_lemma.setdefault(norm(e.word), []).append(e)
            for f in [e.word, *e.variants]:
                self.by_form.setdefault(norm(f), []).append(e)
                self.by_fold.setdefault(fold(norm(f)), []).append(e)
        for e in self.entries:
            e.fixed_level = bool(e.level)
        self._apply_bands()

    def set_bands(self, bands, _recompute: bool = True) -> None:
        """bands: [{level, max_rank}, ...] or {"A1": 600, "A2": 1200, ...}."""
        if isinstance(bands, dict):
            bands = [{"level": k, "max_rank": int(v)} for k, v in bands.items()]
        for b in bands:
            if b["level"] not in self.scale:
                raise ValueError(f"band level {b['level']!r} not in scale {self.scale.levels}")
        self.bands = sorted(bands, key=lambda b: b["max_rank"])
        if _recompute:
            self._apply_bands()

    def _apply_bands(self) -> None:
        for e in self.entries:
            if not e.fixed_level:
                e.level = self.level_for_rank(e.rank)

    # ---- loading -------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path, config: dict, scale: Scale) -> "Vocab":
        path = Path(path)
        text = path.read_text(encoding="utf-8-sig")
        dialect = "excel-tab" if path.suffix.lower() in (".tsv", ".tab", ".txt") else "excel"
        rows = csv.DictReader(text.splitlines(), dialect=dialect)
        cols = {c.strip().lower(): c for c in (rows.fieldnames or [])}
        missing = [c for c in REQUIRED if c not in cols]
        if missing:
            raise ValueError(f"{path}: missing column(s) {missing}; found {list(cols)}")
        sep = config.get("variant_separator", "|")
        entries = []
        for n, row in enumerate(rows, start=2):
            g = lambda c: (row.get(cols[c]) or "").strip() if c in cols else ""
            if not g("rank") or not g("word"):
                continue
            try:
                rank = int(float(g("rank")))
            except ValueError:
                raise ValueError(f"{path}:{n}: rank {g('rank')!r} is not a number") from None
            level = g("level")
            if level and level not in scale:
                raise ValueError(f"{path}:{n}: level {level!r} not in scale {scale.levels}")
            entries.append(Entry(
                rank=rank, word=g("word"), pos=g("pos"), gloss=g("gloss"), level=level,
                variants=[v.strip() for v in g("variants").split(sep) if v.strip()],
                translit=g("translit"), id=g("id") or f"{g('word')}_{g('pos')}",
                feats=g("feats"), tags=parse_tags(g("tags"))))
        if not entries:
            raise ValueError(f"{path}: no entries")
        return cls(entries, config, scale)

    # ---- levels --------------------------------------------------------
    def level_for_rank(self, rank: int) -> str:
        for b in self.bands:
            if rank <= b["max_rank"]:
                return b["level"]
        return self.unranked_level

    def known_as(self, form: str, lemma: str, upos: str) -> bool:
        """Is the word listed with exactly this POS (by lemma or by form)?"""
        for key in (lemma, form):
            if any(e.pos == upos for e in self.by_lemma.get(norm(key), []) + self.by_form.get(norm(key), [])):
                return True
        return any(e.pos == upos for lem in (self.morph.lemmas(form) if self.morph else [])
                   for e in self.by_lemma.get(norm(lem), []))

    def rank_of(self, lemma: str) -> int | None:
        hits = self.by_lemma.get(norm(lemma))
        return min(e.rank for e in hits) if hits else None

    @property
    def unranked_label(self) -> str:
        return f"{self.size}+"

    # ---- lookup --------------------------------------------------------
    def _pos_ok(self, e: Entry, upos: str) -> bool:
        allowed = self.pos_map.get(e.pos)
        return True if allowed is None else upos in allowed

    def _best(self, cands: list[tuple[Entry, int]], upos: str) -> Entry:
        # prefer an exact POS match, then a compatible one, then method priority,
        # then the more frequent entry
        return min(cands, key=lambda c: (not self._pos_ok(c[0], upos), c[0].pos != upos,
                                         c[1], c[0].rank))[0]

    def _direct(self, form: str, lemma: str | None, upos: str) -> tuple[Entry | None, str, int]:
        cands: list[tuple[Entry, int, str]] = []
        # the surface form is itself a headword with a compatible POS: trust it over the
        # parser's lemma (spaCy lemmatises "vosotros" to "tú", for instance)
        cands += [(e, -1, "form") for e in self.by_lemma.get(norm(form), [])
                  if self.pos_map.get(e.pos) and self._pos_ok(e, upos)]
        if lemma:
            cands += [(e, 0, "lemma") for e in self.by_lemma.get(norm(lemma), [])]
        cands += [(e, 1, "variant") for e in self.by_form.get(norm(form), [])
                  if norm(form) != norm(e.word)]
        if self.morph is not None:
            for lem in self.morph.lemmas(form):
                cands += [(e, 1, "morph") for e in self.by_lemma.get(norm(lem), [])]
        cands += [(e, 2, "form") for e in self.by_lemma.get(norm(form), [])]
        if not cands:
            return None, "none", 0
        best = self._best([(e, p) for e, p, _ in cands], upos)
        method = next(m for e, _, m in sorted(cands, key=lambda c: c[1]) if e is best)
        return best, method, len({id(e) for e, _, _ in cands})

    def lookup(self, tok: Token) -> Lookup:
        e, method, n = self._direct(tok.text, tok.lemma, tok.upos)
        if e:
            return Lookup(e, method, n)
        # strip enclitic pronouns (e.g. Spanish dímelo -> dí -> di)
        stem = norm(tok.text)
        for _ in range(3):
            stripped = None
            for pat in self.clitic_patterns:
                m = pat.match(stem)
                if m and m.group(1):
                    stripped = m.group(1)
                    break
            if not stripped:
                break
            stem = stripped
            for cand in dict.fromkeys([stem, fold(stem)]):
                e, _, n = self._direct(cand, None, tok.upos)
                if e:
                    return Lookup(e, "clitic", n)
        if self.accent_fallback:
            hits = self.by_fold.get(fold(norm(tok.text)), [])
            if hits:
                return Lookup(self._best([(h, 0) for h in hits], tok.upos), "folded", len(hits))
        return Lookup(None, "none", 0)

    def excluded(self, tok: Token, sent: Sentence) -> str | None:
        """Reason a token is not ranked at all (punctuation, numbers, names...)."""
        if not any(ch.isalpha() for ch in tok.text):
            return "non-word"
        if any(p.search(tok.text) for p in self.exclude_patterns):
            return "excluded-pattern"
        if tok.feats.get("Foreign") == "Yes":
            return "foreign-script"
        if tok.upos in self.exclude_upos:
            # sentence-initial capitalised common words are often mis-tagged PROPN
            if tok.upos == "PROPN" and tok.i == 0 and self._direct(tok.text, None, "X")[0]:
                return None
            return tok.upos
        return None

"""Morphology lexicon: corrects the parser's verb tagging and lemmas.

Statistical parsers often mis-tag inflected verbs (e.g. Spanish "toques" as a noun,
"llegues" as indicative). The lexicon lists every known analysis of a form
(form, lemma, UPOS, UD features); after parsing, each token is checked against it:

  * parser says VERB/AUX  -> pick the best verb analysis (frequent lemma first,
                             then agreement with the parser) and adopt its
                             lemma + Mood/Tense/VerbForm/Person/Number
  * parser says NOUN/PROPN/X/INTJ but the lexicon only knows the form as a verb
                          -> retag as VERB
  * ...the form can be noun or verb -> retag as VERB only after a "verb cue"
                             (configurable: negation, clitic pronoun, que...)
Adjectives and closed-class words are never retagged.

File: TSV (optionally .gz) with header  form  lemma  upos  feats
"""

from __future__ import annotations

import gzip
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .model import Sentence, Token

VERB_KEYS = ("Mood", "Tense", "VerbForm", "Person", "Number")
RETAGGABLE = {"NOUN", "PROPN", "X", "INTJ"}


class MorphLexicon:
    def __init__(self, index: dict[str, list[tuple[str, str, dict]]]):
        self.index = index

    @classmethod
    def load(cls, path: str | Path) -> "MorphLexicon":
        path = Path(path)
        op = gzip.open if path.suffix == ".gz" else open
        index: dict[str, list] = defaultdict(list)
        feat_cache: dict[str, dict] = {}
        with op(path, "rt", encoding="utf-8") as fh:
            next(fh, None)                       # header
            for line in fh:
                form, lemma, upos, feats = line.rstrip("\n").split("\t")
                f = feat_cache.get(feats)
                if f is None:
                    f = dict(kv.split("=", 1) for kv in feats.split("|") if "=" in kv)
                    feat_cache[feats] = f
                index[form.lower()].append((lemma, upos, f))
        return cls(dict(index))

    def get(self, form: str) -> list[tuple[str, str, dict]]:
        return self.index.get(form.lower(), [])

    def lemmas(self, form: str) -> set[str]:
        return {a[0] for a in self.get(form)}


class MorphCorrector:
    def __init__(self, lex: MorphLexicon, cfg: dict, rank_of: Callable[[str], int | None],
                 clitic_patterns: list[re.Pattern] | None = None,
                 fold: Callable[[str], str] | None = None):
        self.lex = lex
        self.rank_of = rank_of
        self.cues = {c.lower() for c in cfg.get("verb_cues", [])}
        self.pref = cfg.get("mood_preference", ["Ind", "Sub", "Imp", "Cnd"])
        # e.g. {mood: Imp, weight: 2}: a subjectless clause-initial verb leans imperative
        self.initial = cfg.get("initial_subjectless_boost")
        self.clitics = clitic_patterns or []
        self.fold = fold or (lambda s: s)

    def _analyses(self, form: str):
        an = self.lex.get(form)
        if an:
            return an
        # enclitic forms not in the lexicon (dímelo -> díme -> dí -> di): verb readings only
        stem = form.lower()
        for _ in range(3):
            m = next((p.match(stem) for p in self.clitics if p.match(stem)), None)
            if not m:
                break
            stem = m.group(1)
            for cand in dict.fromkeys([stem, self.fold(stem)]):
                an = [a for a in self.lex.get(cand) if a[1] == "VERB"]
                if an:
                    return an
        return []

    def _score(self, a, tok: Token, initial_subjectless: bool):
        """Lower is better: lemma in the frequency list, then agreement with the
        parser's features, then lemma frequency, then configured mood preference."""
        lemma, _, f = a
        r = self.rank_of(lemma)
        agree = sum(1 for k in VERB_KEYS
                    if tok.feats.get(k) is not None and tok.feats.get(k) == f.get(k))
        if initial_subjectless and self.initial and f.get("Mood") == self.initial["mood"]:
            agree += self.initial.get("weight", 2)
        mood = f.get("Mood")
        pref = self.pref.index(mood) if mood in self.pref else len(self.pref)
        return (r is None, -agree, r or 0, lemma.lower() != tok.lemma.lower(), pref)

    def _apply(self, tok: Token, a, upos: str) -> str | None:
        lemma, _, f = a
        before = (tok.upos, tok.lemma, {k: tok.feats.get(k) for k in VERB_KEYS})
        tok.upos = upos
        tok.lemma = lemma
        for k in VERB_KEYS:
            tok.feats.pop(k, None)
        tok.feats.update({k: v for k, v in f.items() if k in VERB_KEYS})
        after = (tok.upos, tok.lemma, {k: tok.feats.get(k) for k in VERB_KEYS})
        if before == after:
            return None
        changed = []
        if before[0] != after[0]:
            changed.append(f"{before[0]}→{after[0]}")
        if before[1] != after[1]:
            changed.append(f"lemma {before[1]}→{after[1]}")
        for k in VERB_KEYS:
            if before[2][k] != after[2][k]:
                changed.append(f"{k} {before[2][k] or '_'}→{after[2][k] or '_'}")
        return "; ".join(changed)

    def correct(self, s: Sentence) -> dict[int, str]:
        fixes: dict[int, str] = {}
        for t in s.tokens:
            an = self._analyses(t.text)
            if not an:
                continue
            verbs = [a for a in an if a[1] == "VERB"]
            if not verbs:
                continue
            # if the lexicon confirms the parser's lemma is possible, trust the lemma
            same = [a for a in verbs if a[0].lower() == t.lemma.lower()]
            first = next((x.i for x in s.tokens if x.upos != "PUNCT"), 0)
            initial = t.i == first and not any(
                c.rel.split(":")[0] == "nsubj" for c in s.children(t.i))
            best = min(same or verbs, key=lambda a: self._score(a, t, initial))
            change = None
            if t.upos in ("VERB", "AUX"):
                change = self._apply(t, best, t.upos)
            elif t.upos in RETAGGABLE:
                nominal = [a for a in an if a[1] != "VERB"]
                prev = next((x for x in reversed(s.tokens[:t.i]) if x.upos != "PUNCT"), None)
                cue = prev is not None and (prev.text.lower() in self.cues or prev.lemma.lower() in self.cues)
                # a capitalised sentence-initial "proper noun" is usually a capitalisation artefact
                cue = cue or (prev is None and t.upos == "PROPN")
                has_det = any(c.upos == "DET" for c in s.children(t.i))
                if not nominal or (cue and not has_det):
                    change = self._apply(t, best, "VERB")
            if change:
                fixes[t.i] = change
        return fixes

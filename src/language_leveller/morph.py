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
                 fold: Callable[[str], str] | None = None,
                 known_as: Callable[[str, str, str], bool] | None = None):
        self.lex = lex
        self.rank_of = rank_of
        self.cues = {c.lower() for c in cfg.get("verb_cues", [])}
        # cues for retagging a listed adjective; narrower, since some cue words are also
        # articles before adjectives (Spanish neuter "lo": lo firme que…)
        self.adj_cues = {c.lower() for c in cfg.get("adj_verb_cues", cfg.get("verb_cues", []))}
        self.pref = cfg.get("mood_preference", ["Ind", "Sub", "Imp", "Cnd"])
        # e.g. {mood: Imp, weight: 2}: a subjectless clause-initial verb leans imperative
        self.initial = cfg.get("initial_subjectless_boost")
        # in languages that capitalise only names mid-sentence, a capitalised word after
        # the first one is never a verb (Rules, Charles in Spanish text)
        self.caps_names = cfg.get("capitalised_midsentence_is_name", False)
        self.clitics = clitic_patterns or []
        self.fold = fold or (lambda s: s)
        # known_as(form, lemma, upos): is this word listed with this POS in the vocab?
        self.known_as = known_as or (lambda f, l, u: False)

    def _analyses(self, form: str):
        self._via_clitic = False
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
                # enclitics attach only to infinitives, gerunds and affirmative
                # imperatives (dímelo, diciéndolo); semejan+te is not a verb form
                an = [a for a in self.lex.get(cand) if a[1] == "VERB" and (
                    a[2].get("VerbForm") in ("Inf", "Ger") or a[2].get("Mood") == "Imp")]
                if an:
                    self._via_clitic = True
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
        first = next((x.i for x in s.tokens if x.upos != "PUNCT"), 0)
        for t in s.tokens:
            if self.caps_names and t.i != first and t.text[:1].isupper():
                # a name, an acronym or a Roman numeral: never a verb
                if t.upos in ("VERB", "AUX") and not t.text.isupper():
                    for k in VERB_KEYS:
                        t.feats.pop(k, None)
                    fixes[t.i] = f"{t.upos}→PROPN (capitalised mid-sentence)"
                    t.upos = "PROPN"
                continue
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
            nominal_listed = [a for a in an if a[1] in ("NOUN", "ADJ") and self.rank_of(a[0]) is not None]
            if (t.upos == "VERB" and nominal_listed and not same
                    and all(self.rank_of(a[0]) is None for a in verbs)):
                # parser says verb, but only an unlisted verb fits while a listed noun or
                # adjective does (heading "Historia": historiar vs historia)
                a = min(nominal_listed, key=lambda a: self.rank_of(a[0]))
                for k in VERB_KEYS:
                    t.feats.pop(k, None)
                fixes[t.i] = f"VERB→{a[1]}; lemma {t.lemma}→{a[0]}"
                t.upos, t.lemma = a[1], a[0]
                continue
            if t.upos in ("VERB", "AUX"):
                change = self._apply(t, best, t.upos)
            elif t.upos == "ADJ" and t.feats.get("VerbForm") == "Part" and not any(
                    a[2].get("VerbForm") == "Part" for a in an):
                # the parser claims a participle the lexicon has never seen (olvido)
                t.feats.pop("VerbForm")
                change = "VerbForm Part→_ (not a participle)"
            elif t.upos == "ADJ":
                # adjectival participles stay ADJ but gain VerbForm=Part for grammar
                # patterns; other verb readings (encierres, controlándolo) are retagged
                # under the same rules as nouns
                nominal = [a for a in an if a[1] != "VERB"]
                if best[2].get("VerbForm") == "Part":
                    if t.feats.get("VerbForm") != "Part":
                        t.feats["VerbForm"] = "Part"
                        change = "VerbForm _→Part"
                else:
                    # a listed adjective (grave, libre, firme) is retagged only after a
                    # verb cue ("No firmes el contrato"); unlisted ones also when the
                    # lexicon knows no nominal reading (encierres, controlándolo)
                    prev = next((x for x in reversed(s.tokens[:t.i]) if x.upos != "PUNCT"), None)
                    cues = self.adj_cues if self.known_as(t.text, t.lemma, "ADJ") else self.cues
                    cue = prev is not None and (prev.text.lower() in cues or prev.lemma.lower() in cues)
                    # without a cue, only forms no adjective can have: infinitive or
                    # gerund (controlándolo); not -e/-es forms that are also subjunctives
                    # of rare verbs (infame/infamar)
                    listed = self.known_as(t.text, t.lemma, "ADJ")
                    if cue or (not listed and not nominal
                               and best[2].get("VerbForm") in ("Inf", "Ger")):
                        change = self._apply(t, best, "VERB")
            elif t.upos in RETAGGABLE:
                nominal = [a for a in an if a[1] != "VERB"]
                prev = next((x for x in reversed(s.tokens[:t.i]) if x.upos != "PUNCT"), None)
                # la/los/las/lo are articles (DET) or clitic pronouns (PRON): only the
                # pronoun is a verb cue; the article is evidence for a noun
                article = prev is not None and prev.upos == "DET"
                # before a word listed as an adjective, lo/la/los/las are articles
                # (a lo largo); before a noun-only word they can only be clitics (no lo toques)
                cues = self.adj_cues if self.known_as(t.text, t.lemma, "ADJ") else self.cues
                cue = prev is not None and not article and (
                    prev.text.lower() in cues or prev.lemma.lower() in cues)
                # a capitalised sentence-initial "proper noun" is usually a capitalisation
                # artefact, unless the vocab lists it as a noun (heading "Historia")
                words = [x for x in s.tokens if x.upos != "PUNCT"]
                if prev is None and t.upos == "PROPN":
                    # sentence-initial capitalised word: a verb only if it has no noun
                    # reading at all; never in a one-word heading (Historia, Bate), an
                    # all-caps token, or a multi-word name (Han Yu)
                    nxt = s.tokens[t.i + 1] if t.i + 1 < len(s.tokens) else None
                    in_name = nxt is not None and nxt.text[:1].isupper()
                    cue = (len(words) > 1 and not nominal and not in_name and not t.text.isupper()
                           and not self.known_as(t.text.lower(), t.text.lower(), "NOUN"))
                # surface evidence for a noun: an article/determiner (not a cue word such
                # as clitic "lo") or a finite verb immediately before it (los toques,
                # sobreviven reportes). Children in the parse are not used: a parser that
                # misreads a verb as a noun also gives it noun-like dependents.
                # a preposition can precede an infinitive (a partir) but not a finite verb
                after_adp = (prev is not None and prev.upos == "ADP"
                             and best[2].get("VerbForm") != "Inf")
                noun_evidence = article or after_adp or (
                    prev is not None and prev.upos in ("VERB", "AUX")
                    and prev.feats.get("VerbForm") == "Fin")
                # without a cue: only when the lexicon knows the form directly and only as a
                # verb, and never for a sentence-initial name (Han Yu)
                sentence_initial_name = prev is None and t.upos == "PROPN"
                no_cue_ok = (not nominal and not self._via_clitic and not sentence_initial_name)
                if not noun_evidence and (cue or no_cue_ok):
                    change = self._apply(t, best, "VERB")
            if change:
                fixes[t.i] = change
        return fixes

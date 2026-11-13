"""Language Leveller: the core process.

    text -> clean segments -> parsed sentences -> per-word rank/level
         -> grammar features/level -> one record per sentence
"""

from __future__ import annotations

from pathlib import Path

from . import yamlio
from .cleaner import Cleaner
from .grammar import GrammarProfile
from .levels import Scale
from .model import Segment, Sentence
from .morph import MorphCorrector, MorphLexicon
from .parsing import Parser, load_parser
from .vocab import Vocab, fold, norm


class Leveller:
    def __init__(self, config: dict, vocab: Vocab, grammar: GrammarProfile,
                 parser: Parser, scale: Scale, morph: MorphLexicon | None = None):
        self.cfg = config
        self.vocab = vocab
        self.grammar = grammar
        self.parser = parser
        self.scale = scale
        self.corrector = None
        if morph is not None:
            vocab.morph = morph
            self.corrector = MorphCorrector(morph, config.get("morph") or {}, vocab.rank_of,
                                            vocab.clitic_patterns, fold, vocab.known_as)
        scoring = config.get("scoring") or {}
        self.unranked_counts = scoring.get("unranked_counts", True)
        self.low_coverage = scoring.get("low_coverage_threshold", 0.5)
        self.cleaner = Cleaner(config.get("cleaning") or {},
                               known_form=lambda w: norm(w) in vocab.by_form or bool(
                                   vocab.morph and vocab.morph.get(w)))

    # ---- construction --------------------------------------------------------
    @classmethod
    def from_dir(cls, lang_dir: str | Path, vocab_path: str | Path | None = None,
                 grammar_path: str | Path | None = None,
                 parser: Parser | str | list[str] | None = None,
                 morph_path: str | Path | bool | None = None,
                 bands: list | dict | None = None) -> "Leveller":
        """Build from a language directory containing config.yaml.
        Explicit paths/parser override what the config names."""
        lang_dir = Path(lang_dir)
        cfg = yamlio.load(lang_dir / "config.yaml")
        scale = Scale(cfg.get("levels"))
        vcfg = cfg.get("vocab") or {}
        gcfg = cfg.get("grammar") or {}
        vpath = Path(vocab_path) if vocab_path else lang_dir / vcfg.get("file", "vocab.tsv")
        if not vpath.exists() and vcfg.get("fallback_file"):
            vpath = lang_dir / vcfg["fallback_file"]
        gpath = Path(grammar_path) if grammar_path else lang_dir / gcfg.get("file", "grammar.yaml")
        vocab = Vocab.load(vpath, vcfg, scale)
        if bands:
            vocab.set_bands(bands)
        grammar = GrammarProfile.load(gpath, scale)
        if parser is None or isinstance(parser, (str, list)):
            parser = load_parser(parser or cfg.get("parser") or [])
        morph = None
        mcfg = cfg.get("morph") or {}
        if morph_path is not False:
            mpath = Path(morph_path) if morph_path else (
                lang_dir / mcfg["file"] if mcfg.get("file") else None)
            if mpath and mpath.exists():
                morph = MorphLexicon.load(mpath)
        return cls(cfg, vocab, grammar, parser, scale, morph)

    # ---- processing ----------------------------------------------------------
    def level_text(self, text: str, fmt: str = "auto") -> list[dict]:
        records = []
        for seg in self.cleaner.segments(text, fmt):
            sents = self.parser.parse(seg.clean)
            # each removed/rewritten item goes to the last sentence starting at or before it
            per_sent: list[list[dict]] = [[] for _ in sents]
            for item in seg.ignored if sents else []:
                n = max((j for j, st in enumerate(sents) if st.start <= item.get("pos", 0)), default=0)
                per_sent[n].append(item)
            for sent, items in zip(sents, per_sent):
                records.append(self.level_sentence(sent, seg, items))
        return records

    def level_sentence(self, sent: Sentence, seg: Segment | None = None,
                       ignored: list[dict] | None = None) -> dict:
        fixes = self._annotate(sent)
        tokens, levels, unranked, rankable, found = [], [], [], 0, 0
        max_rank = 0
        for t in sent.tokens:
            rec = {"i": t.i, "text": t.text, "lemma": t.lemma, "upos": t.upos}
            feats = "|".join(f"{k}={v}" for k, v in sorted(t.feats.items()))
            if feats:
                rec["feats"] = feats
            if t.i in fixes:
                rec["morph_fix"] = fixes[t.i]
            reason = self.vocab.excluded(t, sent)
            if reason:
                rec["excluded"] = reason
            else:
                rankable += 1
                lk = self.vocab.lookup(t)
                if lk.entry:
                    e = lk.entry
                    found += 1
                    max_rank = max(max_rank, e.rank)
                    levels.append(e.level)
                    rec.update(id=e.id, headword=e.word, rank=e.rank, level=e.level, pos=e.pos,
                               gloss=e.gloss, match=lk.method)
                    if e.feats:
                        rec["lex_feats"] = e.feats
                    if e.tags:
                        rec["tags"] = e.tags
                    if e.translit:
                        rec["translit"] = e.translit
                    if lk.candidates > 1:
                        rec["ambiguous"] = lk.candidates
                else:
                    rec.update(rank=self.vocab.unranked_label,
                               level=self.vocab.unranked_level, match="none")
                    unranked.append(t.text)
                    if self.unranked_counts:
                        levels.append(self.vocab.unranked_level)
            tokens.append(rec)

        g_level, g_matches = self.grammar.analyse(sent)
        v_level = self.scale.max(levels) or self.scale.levels[0]
        coverage = round(found / rankable, 3) if rankable else None
        # share of all alphabetic tokens (names included) found in the list:
        # catches foreign-language lines whose words all get tagged as names
        alpha = sum(1 for t in sent.tokens if any(ch.isalpha() for ch in t.text))

        flags = list(seg.flags) if seg else []
        ignored = ignored if ignored is not None else (seg.ignored if seg else [])
        if self.cleaner.internet_text(ignored):
            flags.append("internet_text")
        if alpha and found / alpha < self.low_coverage:
            flags.append("low_coverage")
        if not any(t.upos in ("VERB", "AUX") for t in sent.tokens):
            flags.append("no_verb")
        if rankable < 3:
            flags.append("short")

        rec = {
            "text": sent.text,
            "level": self.scale.max([v_level, g_level]),
            "vocab": {"level": v_level, "max_rank": max_rank or None,
                      "coverage": coverage, "unranked": unranked},
            "grammar": {"level": g_level,
                        "features": [dict({"id": m.id, "level": m.level, "label": m.label,
                                           "tokens": m.tokens},
                                          **({"regions": m.regions} if m.regions else {}))
                                     for m in g_matches]},
            "tokens": tokens,
            "flags": flags,
        }
        if seg:
            rec["source"] = {"original": seg.original, "start": seg.start, "end": seg.end}
            if ignored:
                rec["source"]["ignored"] = [{k: v for k, v in i.items() if k != "pos"}
                                            for i in ignored]
        return rec

    def _annotate(self, sent: Sentence) -> dict[int, str]:
        """Pre-grammar annotation: morphology correction, then vocabulary-derived
        features grammar patterns can use. `Lexicalised=Yes` marks a participle the
        vocab lists as an adjective (cansado, abierto), i.e. learnt as a word rather
        than formed productively (tomado, firmado)."""
        fixes = self.corrector.correct(sent) if self.corrector else {}
        for t in sent.tokens:
            if t.feats.get("VerbForm") == "Part" and self.vocab.known_as(t.text, t.lemma, "ADJ"):
                t.feats["Lexicalised"] = "Yes"
        return fixes

    # ---- grammar self-test -----------------------------------------------------
    def test_grammar(self) -> list[dict]:
        """Run every feature's tests.pos / tests.neg sentences through the parser."""
        results = []
        for f in self.grammar.features:
            for kind in ("pos", "neg"):
                for text in f.tests.get(kind, []) or []:
                    sents = self.parser.parse(text)
                    for s in sents:
                        self._annotate(s)
                    hit = any(f.find(s) for s in sents)
                    ok = hit if kind == "pos" else not hit
                    results.append({"feature": f.id, "kind": kind, "text": text, "ok": ok})
        return results

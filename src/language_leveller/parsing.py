"""Parser backends. Each turns plain text into Sentences of UD-annotated Tokens.

Backends:
  spacy:<model>    e.g. spacy:es_core_news_md
  stanza:<lang>    e.g. stanza:es   (models download on first use)
  conllu           reads pre-parsed CoNLL-U (any UD parser, e.g. UDPipe)
"""

from __future__ import annotations

from typing import Iterable, Protocol

from .model import Sentence, Token


class Parser(Protocol):
    def parse(self, text: str) -> list[Sentence]: ...


def _feats(s: str) -> dict[str, str]:
    if not s or s == "_":
        return {}
    out = {}
    for part in s.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


class SpacyParser:
    def __init__(self, model: str):
        import spacy
        self.nlp = spacy.load(model)

    def parse(self, text: str) -> list[Sentence]:
        doc = self.nlp(text)
        out = []
        for sent in doc.sents:
            base = sent.start
            cbase = sent.start_char
            toks = []
            for t in sent:
                if t.is_space:
                    continue
                rel = t.dep_.lower()
                if rel == "root":
                    rel = "root"
                toks.append(Token(
                    i=t.i - base, text=t.text, lemma=t.lemma_, upos=t.pos_,
                    feats=_feats(str(t.morph)), head=t.head.i - base, rel=rel,
                    start=t.idx - cbase, end=t.idx - cbase + len(t.text)))
            # re-index after dropping whitespace tokens
            _reindex(toks)
            out.append(Sentence(text=sent.text, tokens=toks))
        return out


class StanzaParser:
    def __init__(self, lang: str):
        import stanza
        self.nlp = stanza.Pipeline(lang, processors="tokenize,mwt,pos,lemma,depparse",
                                   verbose=False)

    def parse(self, text: str) -> list[Sentence]:
        doc = self.nlp(text)
        out = []
        for sent in doc.sentences:
            toks = []
            cbase = sent.tokens[0].start_char if sent.tokens else 0
            for w in sent.words:
                tok = w.parent
                toks.append(Token(
                    i=w.id - 1, text=w.text, lemma=w.lemma or w.text, upos=w.upos,
                    feats=_feats(w.feats or ""), head=(w.head - 1) if w.head else w.id - 1,
                    rel=w.deprel, start=(tok.start_char or 0) - cbase,
                    end=(tok.end_char or 0) - cbase))
            out.append(Sentence(text=sent.text, tokens=toks))
        return out


def parse_conllu(data: str) -> list[Sentence]:
    """Parse CoNLL-U text. Multiword-token lines (1-2) and empty nodes (1.1) are skipped."""
    sents, toks, text = [], [], ""
    for line in data.splitlines() + [""]:
        line = line.rstrip("\n")
        if not line.strip():
            if toks:
                sents.append(Sentence(text=text or " ".join(t.text for t in toks), tokens=toks))
            toks, text = [], ""
            continue
        if line.startswith("#"):
            if line.startswith("# text ="):
                text = line.split("=", 1)[1].strip()
            continue
        cols = line.split("\t")
        if "-" in cols[0] or "." in cols[0]:
            continue
        idx, head = int(cols[0]) - 1, int(cols[6]) if cols[6] != "_" else 0
        toks.append(Token(i=idx, text=cols[1], lemma=cols[2], upos=cols[3],
                          feats=_feats(cols[5]), head=(head - 1) if head else idx,
                          rel=cols[7]))
    return sents


class ConlluParser:
    """Treats the input text itself as CoNLL-U."""
    def parse(self, text: str) -> list[Sentence]:
        return parse_conllu(text)


def _reindex(toks: list[Token]) -> None:
    mapping = {t.i: n for n, t in enumerate(toks)}
    for t in toks:
        t.i = mapping[t.i]
        t.head = mapping.get(t.head, t.i)


def load_parser(spec: str | Iterable[str]) -> Parser:
    """Load the first available backend from a spec or list of specs."""
    specs = [spec] if isinstance(spec, str) else list(spec)
    errors = []
    for s in specs:
        kind, _, arg = s.partition(":")
        try:
            if kind == "spacy":
                return SpacyParser(arg)
            if kind == "stanza":
                return StanzaParser(arg)
            if kind == "conllu":
                return ConlluParser()
            errors.append(f"{s}: unknown backend")
        except Exception as e:  # missing package or model: try the next one
            errors.append(f"{s}: {e}")
    raise RuntimeError("No parser backend could be loaded:\n  " + "\n  ".join(errors))

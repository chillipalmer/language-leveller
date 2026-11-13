"""Grammar profile: loads a YAML file of levelled grammar features and matches them
against UD-parsed sentences. The pattern language is described in docs/FORMATS.md.

Three pattern kinds:
  token:    one token satisfying a constraint
  graph:    named tokens linked by dependency relations (head: <other node>)
  sequence: consecutive tokens, with optional gaps and back-references
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import yamlio

from .levels import Scale
from .model import Sentence, Token

# keys in a constraint that are not UD morphological features
STRUCTURAL = {"form", "lemma", "upos", "rel", "regex", "sent_start", "clause_start", "has_child",
              "no_child", "head_is", "as", "same_form", "same_lemma", "optional", "gap"}


class PatternError(ValueError):
    pass


# ---------------------------------------------------------------------------
# constraint evaluation
# ---------------------------------------------------------------------------
def _as_set(v) -> set[str]:
    if v is None:
        return set()
    if isinstance(v, (list, tuple, set)):
        return {str(x) for x in v}
    return {str(v)}


def _value_test(spec, actual: set[str], fold=lambda s: s) -> bool:
    """spec: scalar | list (any of) | {not: scalar|list}. `actual` is the token's value set."""
    actual = {fold(a) for a in actual}
    if isinstance(spec, dict):
        if set(spec) != {"not"}:
            raise PatternError(f"only {{not: ...}} allowed as a value, got {spec}")
        return not (actual & {fold(x) for x in _as_set(spec["not"])})
    if spec is None or spec == "_":         # feature must be absent
        return not actual
    return bool(actual & {fold(x) for x in _as_set(spec)})


def _rel_values(rel: str) -> set[str]:
    # "aux:pass" satisfies both "aux:pass" and "aux"
    return {rel, rel.split(":")[0]}


def token_ok(c: dict, t: Token, s: Sentence, binds: dict | None = None) -> bool:
    low = str.lower
    for k, v in c.items():
        if k in ("as", "optional"):
            continue
        if k == "form":
            ok = _value_test(v, {t.text}, low)
        elif k == "lemma":
            ok = _value_test(v, {t.lemma}, low)
        elif k == "upos":
            ok = _value_test(v, {t.upos})
        elif k == "rel":
            ok = _value_test(v, _rel_values(t.rel.lower()), low)
        elif k == "regex":
            ok = re.search(v, t.text.lower()) is not None
        elif k == "sent_start":
            first = next((x.i for x in s.tokens if x.upos != "PUNCT"), 0)
            ok = (t.i == first) == bool(v)
        elif k == "clause_start":
            # first word of the sentence, or first word after , ; : — ( etc.
            first = next((x.i for x in s.tokens if x.upos != "PUNCT"), 0)
            prev = s.tokens[t.i - 1] if t.i > 0 else None
            ok = (t.i == first or (prev is not None and prev.upos == "PUNCT")) == bool(v)
        elif k == "has_child":
            ok = any(token_ok(v, ch, s) for ch in s.children(t.i))
        elif k == "no_child":
            ok = not any(token_ok(v, ch, s) for ch in s.children(t.i))
        elif k == "head_is":
            ok = t.head != t.i and token_ok(v, s.tokens[t.head], s)
        elif k == "same_form":
            ok = binds is not None and v in binds and binds[v].text.lower() == t.text.lower()
        elif k == "same_lemma":
            ok = binds is not None and v in binds and binds[v].lemma.lower() == t.lemma.lower()
        else:                                # UD morphological feature
            ok = _value_test(v, t.feat_values(k))
        if not ok:
            return False
    return True


# ---------------------------------------------------------------------------
# pattern matchers: each yields lists of matched token indices
# ---------------------------------------------------------------------------
def match_token(c: dict, s: Sentence):
    for t in s.tokens:
        if token_ok(c, t, s):
            yield [t.i]


def match_graph(nodes: dict, s: Sentence):
    names = list(nodes)

    def solve(k: int, bound: dict[str, Token]):
        if k == len(names):
            yield dict(bound)
            return
        name = names[k]
        spec = dict(nodes[name] or {})
        head = spec.pop("head", None)
        used = {b.i for b in bound.values()}
        for t in s.tokens:
            if t.i in used or not token_ok(spec, t, s):
                continue
            if head is not None:
                if head in bound:
                    if t.head != bound[head].i or t.i == t.head:
                        continue
                elif head not in names:
                    raise PatternError(f"graph node {name!r}: unknown head {head!r}")
            bound[name] = t
            # check later nodes that name this one as head lazily; also nodes bound
            # earlier whose head is this node
            if all(nodes[n].get("head") != name or bound[n].head == t.i
                   for n in bound if n != name):
                yield from solve(k + 1, bound)
            del bound[name]

    for b in solve(0, {}):
        yield sorted(t.i for t in b.values())


def match_sequence(elems: list, s: Sentence):
    toks = s.tokens

    def step(k: int, pos: int, binds: dict, got: list[int]):
        if k == len(elems):
            yield got
            return
        e = elems[k]
        if "gap" in e:
            lo, hi = e["gap"] if isinstance(e["gap"], list) else (0, e["gap"])
            for g in range(lo, hi + 1):
                if pos + g <= len(toks):
                    yield from step(k + 1, pos + g, binds, got)
            return
        if e.get("optional"):
            yield from step(k + 1, pos, binds, got)
        if pos < len(toks) and token_ok(e, toks[pos], s, binds):
            nb = dict(binds)
            if "as" in e:
                nb[e["as"]] = toks[pos]
            yield from step(k + 1, pos + 1, nb, got + [toks[pos].i])

    for start in range(len(toks)):
        for m in step(0, start, {}, []):
            if m:
                yield m
                break


def run_pattern(p: dict, s: Sentence):
    if not isinstance(p, dict) or len(p) != 1:
        raise PatternError(f"a pattern needs exactly one of token/graph/sequence, got {p}")
    kind, body = next(iter(p.items()))
    if kind == "token":
        return match_token(body, s)
    if kind == "graph":
        return match_graph(body, s)
    if kind == "sequence":
        return match_sequence(body, s)
    raise PatternError(f"unknown pattern kind {kind!r}")


# ---------------------------------------------------------------------------
# features and profile
# ---------------------------------------------------------------------------
@dataclass
class Feature:
    id: str
    level: str
    label: str
    patterns: list[dict]
    description: str = ""
    tests: dict = field(default_factory=dict)
    regions: list[str] = field(default_factory=list)   # empty = all regions
    exceptions: list[dict] = field(default_factory=list)  # matches overlapping these are dropped

    def find(self, s: Sentence) -> list[list[int]]:
        blocked: set[int] = set()
        for p in self.exceptions:
            for m in run_pattern(p, s):
                blocked.update(m)
        hits, seen = [], set()
        for p in self.patterns:
            for m in run_pattern(p, s):
                key = tuple(m)
                if key not in seen and not blocked.intersection(m):
                    seen.add(key)
                    hits.append(m)
        return hits


@dataclass
class Match:
    id: str
    level: str
    label: str
    tokens: list[list[int]]
    regions: list[str] = field(default_factory=list)


class GrammarProfile:
    def __init__(self, data: dict, scale: Scale, source: str = "<grammar>"):
        self.source = source
        self.scale = scale
        self.language = data.get("language", "")
        self.default_level = data.get("default_level", scale.levels[0])
        self.features: list[Feature] = []
        ids = set()
        for n, f in enumerate(data.get("features") or []):
            where = f"{source}: feature #{n + 1} ({f.get('id', '?')})"
            for k in ("id", "level", "label"):
                if k not in f:
                    raise PatternError(f"{where}: missing '{k}'")
            if f["id"] in ids:
                raise PatternError(f"{where}: duplicate id")
            ids.add(f["id"])
            if f["level"] not in scale:
                raise PatternError(f"{where}: level {f['level']!r} not in scale")
            pats = f.get("match_any") or ([f["match"]] if "match" in f else [])
            if not pats:
                raise PatternError(f"{where}: needs 'match' or 'match_any'")
            if f.get("enabled", True):
                regions = f.get("regions") or []
                self.features.append(Feature(f["id"], f["level"], f["label"], pats,
                                             f.get("description", ""), f.get("tests") or {},
                                             [regions] if isinstance(regions, str) else list(regions),
                                             f.get("except") or []))
        self.combinations = data.get("combinations") or []
        for c in self.combinations:
            for k in ("id", "level", "min_distinct", "result", "label"):
                if k not in c:
                    raise PatternError(f"{source}: combination missing '{k}': {c}")

    @classmethod
    def load(cls, path: str | Path, scale: Scale) -> "GrammarProfile":
        path = Path(path)
        return cls(yamlio.load(path), scale, str(path))

    def analyse(self, s: Sentence) -> tuple[str, list[Match]]:
        found = []
        for f in self.features:
            hits = f.find(s)
            if hits:
                found.append(Match(f.id, f.level, f.label, hits, f.regions))
        for c in self.combinations:
            distinct = [m for m in found if m.level == c["level"]]
            if len(distinct) >= c["min_distinct"]:
                found.append(Match(c["id"], c["result"], c["label"],
                                   [sorted({i for m in distinct for h in m.tokens for i in h})]))
        level = self.scale.max([self.default_level] + [m.level for m in found])
        return level, found

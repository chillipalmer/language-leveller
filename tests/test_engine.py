"""Engine tests on hand-written CoNLL-U: no parser model needed."""

import pytest

from language_leveller import yamlio
from language_leveller.grammar import GrammarProfile, PatternError
from language_leveller.levels import Scale
from language_leveller.morph import MorphCorrector, MorphLexicon
from language_leveller.parsing import parse_conllu
from language_leveller.vocab import Entry, Vocab

SCALE = Scale()

# "Si hubiera sabido, no habría venido."
CONLLU = """# text = Si hubiera sabido, no habría venido.
1\tSi\tsi\tSCONJ\t_\t_\t3\tmark\t_\t_
2\thubiera\thaber\tAUX\t_\tMood=Sub|Number=Sing|Person=3|Tense=Imp|VerbForm=Fin\t3\taux\t_\t_
3\tsabido\tsaber\tVERB\t_\tGender=Masc|Number=Sing|Tense=Past|VerbForm=Part\t7\tadvcl\t_\t_
4\t,\t,\tPUNCT\t_\t_\t3\tpunct\t_\t_
5\tno\tno\tADV\t_\tPolarity=Neg\t7\tadvmod\t_\t_
6\thabría\thaber\tAUX\t_\tMood=Cnd|Number=Sing|Person=3|VerbForm=Fin\t7\taux\t_\t_
7\tvenido\tvenir\tVERB\t_\tGender=Masc|Number=Sing|Tense=Past|VerbForm=Part\t0\troot\t_\t_
8\t.\t.\tPUNCT\t_\t_\t7\tpunct\t_\t_
"""


def sent():
    return parse_conllu(CONLLU)[0]


def profile(yaml_text):
    return GrammarProfile(yamlio.loads(yaml_text), SCALE)


def test_conllu_reader():
    s = sent()
    assert len(s.tokens) == 8
    assert s.tokens[1].feats["Mood"] == "Sub"
    assert s.tokens[1].head == 2 and s.tokens[6].head == 6


def test_token_graph_sequence_and_level():
    g = profile("""
default_level: A1
features:
  - {id: t, level: B2, label: imp subj, match: {token: {Mood: Sub, Tense: Imp}}}
  - id: g
    level: B2
    label: cond perfect
    match: {graph: {v: {VerbForm: Part}, aux: {lemma: haber, Mood: Cnd, rel: aux, head: v}}}
  - {id: s, level: A2, label: no + aux, match: {sequence: [{form: no}, {upos: AUX}]}}
  - {id: miss, level: C2, label: never, match: {token: {Mood: Imp}}}
""")
    level, matches = g.analyse(sent())
    assert {m.id for m in matches} == {"t", "g", "s"}
    assert level == "B2"
    assert next(m for m in matches if m.id == "g").tokens == [[5, 6]]


def test_bare_no_is_a_word_not_false():
    # YAML 1.1 would read `no` as False; our loader must keep it a string
    assert yamlio.loads("x: [no, on, yes, si]")["x"] == ["no", "on", "yes", "si"]
    assert yamlio.loads("x: true")["x"] is True


def test_negation_list_and_absent_values():
    g = profile("""
features:
  - {id: a, level: B1, label: non-haber aux, match: {token: {upos: AUX, lemma: {not: [haber]}}}}
  - {id: b, level: A2, label: no mood, match: {token: {upos: VERB, Mood: null, VerbForm: Part}}}
""")
    _, m = g.analyse(sent())
    assert {x.id for x in m} == {"b"}


def test_rel_subtypes_match_base_relation():
    s = sent()
    s.tokens[1].rel = "aux:pass"
    g = profile("""
features:
  - {id: a, level: B1, label: x, match: {graph: {v: {}, a: {rel: aux, lemma: haber, Mood: Sub, head: v}}}}
""")
    assert g.analyse(s)[1]


def test_sequence_gap_backreference_optional():
    s = parse_conllu("""1\tPase\tpasar\tVERB\t_\tMood=Sub\t0\troot\t_\t_
2\tlo\tél\tPRON\t_\t_\t1\tobj\t_\t_
3\tque\tque\tPRON\t_\t_\t4\tnsubj\t_\t_
4\tpase\tpasar\tVERB\t_\tMood=Sub\t1\tacl\t_\t_
""")[0]
    g = profile("""
features:
  - id: r
    level: C1
    label: redup
    match: {sequence: [{Mood: Sub, as: V}, {gap: [1, 2]}, {same_form: V}]}
  - id: o
    level: B1
    label: optional
    match: {sequence: [{form: lo}, {form: el, optional: true}, {form: que}]}
""")
    _, m = g.analyse(s)
    assert {x.id for x in m} == {"r", "o"}


def test_combination_rule():
    g = profile("""
combinations: [{id: c, level: B2, min_distinct: 2, result: C2, label: two B2}]
features:
  - {id: t, level: B2, label: a, match: {token: {Mood: Sub}}}
  - {id: u, level: B2, label: b, match: {token: {Mood: Cnd}}}
""")
    level, m = g.analyse(sent())
    assert level == "C2" and "c" in {x.id for x in m}


def test_profile_validation():
    with pytest.raises(PatternError):
        profile("features: [{id: a, level: Z9, label: x, match: {token: {}}}]")
    with pytest.raises(PatternError):
        profile("features: [{id: a, level: A1, label: x}]")


def _vocab(**cfg):
    entries = [Entry(1, "venir", "v", variants=["vengas", "ven"]), Entry(5, "decir", "v", variants=["di"]),
               Entry(9, "como", "conj"), Entry(30, "comer", "v", variants=["como"]),
               Entry(1500, "está", "v")]
    base = {"bands": [{"level": "A1", "max_rank": 10}, {"level": "A2", "max_rank": 2000}],
            "pos_map": {"v": ["VERB", "AUX"], "conj": ["SCONJ", "CCONJ"]},
            "clitic_suffixes": ["^(.{2,}?)(nos|os|me|te|se|lo|la|le|los|las|les)$"]}
    base.update(cfg)
    return Vocab(entries, base, SCALE)


def test_vocab_bands_and_lookup_methods():
    v = _vocab()
    tok = lambda text, lemma, upos: parse_conllu(f"1\t{text}\t{lemma}\t{upos}\t_\t_\t0\troot\t_\t_")[0].tokens[0]
    assert v.lookup(tok("vengas", "vengas", "VERB")).entry.word == "venir"       # variant
    assert v.lookup(tok("vengas", "vengas", "VERB")).method == "variant"
    assert v.lookup(tok("dímelo", "dímelir", "VERB")).method == "clitic"         # díme-lo -> dí-me -> di
    assert v.lookup(tok("como", "como", "SCONJ")).entry.word == "como"           # POS picks homograph
    assert v.lookup(tok("como", "comer", "VERB")).entry.word == "comer"
    assert v.lookup(tok("esta", "este", "VERB")).method == "folded"              # missing accent
    assert v.lookup(tok("xyz", "xyz", "NOUN")).entry is None
    assert v.level_for_rank(1) == "A1" and v.level_for_rank(1500) == "A2"
    assert v.level_for_rank(9999) == "C2+" and v.unranked_label == "1500+"


def test_morph_corrector_retags_and_prefers_listed_lemma():
    lex = MorphLexicon({
        "toques": [("tocar", "VERB", {"Mood": "Sub", "Tense": "Pres", "Person": "2", "Number": "Sing", "VerbForm": "Fin"}),
                   ("toque", "NOUN", {"Number": "Plur"})],
        "vengas": [("vengar", "VERB", {"Mood": "Ind", "Tense": "Pres", "Person": "2", "VerbForm": "Fin"}),
                   ("venir", "VERB", {"Mood": "Sub", "Tense": "Pres", "Person": "2", "VerbForm": "Fin"})],
    })
    ranks = {"tocar": 100, "venir": 50}
    c = MorphCorrector(lex, {"verb_cues": ["no"]}, ranks.get)
    s = parse_conllu("""1\tNo\tno\tADV\t_\tPolarity=Neg\t2\tadvmod\t_\t_
2\ttoques\ttoque\tNOUN\t_\tNumber=Plur\t0\troot\t_\t_
3\tvengas\tvengas\tVERB\t_\tMood=Ind|Tense=Pres|VerbForm=Fin\t2\tconj\t_\t_
""")[0]
    fixes = c.correct(s)
    assert s.tokens[1].upos == "VERB" and s.tokens[1].feats["Mood"] == "Sub"
    assert s.tokens[2].lemma == "venir" and s.tokens[2].feats["Mood"] == "Sub"
    assert set(fixes) == {1, 2}
    # without the cue a noun reading is kept
    s2 = parse_conllu("1\ttoques\ttoque\tNOUN\t_\t_\t0\troot\t_\t_")[0]
    assert not c.correct(s2) and s2.tokens[0].upos == "NOUN"


def test_band_override_and_tags():
    from language_leveller.vocab import parse_tags
    v = _vocab()
    assert v.level_for_rank(30) == "A2"
    v.set_bands({"A1": 40, "A2": 2000})
    assert v.level_for_rank(30) == "A1"
    assert next(e for e in v.entries if e.word == "comer").level == "A1"
    assert parse_tags("region=CL,AR; register=colloquial") == {
        "region": ["CL", "AR"], "register": ["colloquial"]}


def test_regional_feature_reports_regions():
    g = profile("""
features:
  - {id: r, level: A1, label: regional, regions: [ES], match: {token: {Mood: Sub}}}
""")
    _, m = g.analyse(sent())
    assert m[0].regions == ["ES"]

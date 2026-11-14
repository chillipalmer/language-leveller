"""Integration tests for the Spanish profile. Skipped if spaCy or its model is missing."""

from pathlib import Path

import pytest

ES = Path(__file__).resolve().parents[1] / "languages" / "es"

spacy = pytest.importorskip("spacy")
try:
    spacy.load("es_core_news_md")
except OSError:
    pytest.skip("es_core_news_md not installed", allow_module_level=True)

from language_leveller import Leveller  # noqa: E402


@pytest.fixture(scope="module")
def ll():
    return Leveller.from_dir(ES)


def test_grammar_profile_self_tests(ll):
    bad = [r for r in ll.test_grammar() if not r["ok"]]
    assert not bad, "\n".join(f"{r['feature']} [{r['kind']}]: {r['text']}" for r in bad)


@pytest.mark.parametrize("text,level", [
    ("Vivo en Madrid.", "A1"),
    ("Ayer comí paella.", "A2"),
    ("Quiero que vengas mañana.", "B1"),
    ("Si hubiera sabido la verdad, no habría venido.", "B2"),
    ("Pase lo que pase, te llamo.", "C1"),
    ("Sea como fuere, lo haremos.", "C2"),
])
def test_grammar_levels(ll, text, level):
    assert ll.level_text(text)[0]["grammar"]["level"] == level


def test_two_c1_structures_make_c2(ll):
    r = ll.level_text("De no ser por ti, fue Juan quien lo dijo.")[0]
    assert r["grammar"]["level"] == "C2"


def test_record_shape_and_internet_text(ll):
    recs = ll.level_text("Holaaa!! q tal?? 😂 @ana\nNo me lo digas xq ya lo sé")
    assert len(recs) == 2
    r = recs[1]
    assert r["text"] == "No me lo digas porque ya lo sé"
    assert r["grammar"]["level"] == "B1"
    assert {"text", "level", "vocab", "grammar", "tokens", "flags", "source"} <= set(r)
    digas = next(t for t in r["tokens"] if t["text"] == "digas")
    assert digas["headword"] == "decir" and digas["level"] == "A1"
    assert any(i["type"] == "abbreviation" for i in r["source"]["ignored"])


def test_ignored_items_attach_to_their_own_sentence(ll):
    recs = ll.level_text("holaaa q tal?? 😂 mañana vamos a la playa #verano")
    assert len(recs) == 2
    first = {i["text"] for i in recs[0]["source"]["ignored"]}
    second = {i["text"] for i in recs[1]["source"]["ignored"]}
    assert first == {"holaaa", "q", "😂"} and second == {"#verano"}
    assert "internet_text" in recs[0]["flags"] and "internet_text" in recs[1]["flags"]


def test_unranked_words_and_names(ll):
    r = ll.level_text("María compró un ornitorrinco.")[0]
    toks = {t["text"]: t for t in r["tokens"]}
    assert toks["María"].get("excluded") == "PROPN"
    assert toks["ornitorrinco"]["rank"].endswith("+")
    assert r["vocab"]["level"] == "C2+" and "ornitorrinco" in r["vocab"]["unranked"]


def test_foreign_line_is_flagged(ll):
    assert "low_coverage" in ll.level_text("Check this out.")[0]["flags"]


def test_complexity_is_reported_and_grows_with_structure(ll):
    simple = ll.level_text("Vivo en Madrid.")[0]["complexity"]
    hard = ll.level_text("Si hubiera sabido que ibas a venir cuando terminaras el trabajo, "
                         "te habría preparado la paella que tanto te gusta.")[0]["complexity"]
    assert simple["words"] == 3 and simple["clauses"] == 1
    assert hard["clauses"] >= 4 and hard["depth"] > simple["depth"]
    assert hard["mean_dep_distance"] > simple["mean_dep_distance"]


def test_items_list_for_learner_matching(ll):
    r = ll.level_text("No creo que venga mañana con el bateador.")[0]
    items = r["items"]
    lemmas = {i["id"]: i for i in items if i["kind"] == "lemma"}
    grammar = {i["id"] for i in items if i["kind"] == "grammar"}
    assert {"no_ADV", "creer_VERB", "venir_VERB", "el_DET"} <= set(lemmas)
    assert "Mood=Sub" in lemmas["venir_VERB"]["feats"]
    # unlisted word: stable id, flagged, still an item
    assert lemmas["bateador_NOUN"]["listed"] is False
    assert "listed" not in lemmas["venir_VERB"]
    assert "es.subj.present" in grammar
    # punctuation is not an item; duplicates collapse
    assert all(i["id"] != "._PUNCT" for i in items)
    r2 = ll.level_text("La casa y la casa.")[0]
    assert sum(1 for i in r2["items"] if i["id"] == "casa_NOUN") == 1


def _tok(r, text):
    return next(t for t in r["tokens"] if t["text"] == text)


def test_sentence_initial_name_before_a_verb_is_not_a_verb(ll):
    # "Tomás" is also tomar (2sg); followed by a finite verb it is that verb's subject
    r = ll.level_text("Tomás tiene 70 años.")[0]
    t = _tok(r, "Tomás")
    assert t["upos"] == "PROPN" and t.get("headword") is None
    # a sentence-initial verb is still a verb
    assert _tok(ll.level_text("Mira la carta.")[0], "Mira")["upos"] == "VERB"


def test_verb_after_its_subject_is_not_imperative(ll):
    r = ll.level_text("Andrés mira por la ventana.")[0]
    assert _tok(r, "mira")["feats"].startswith("Mood=Ind")
    assert "es.imperative.affirmative" not in {f["id"] for f in r["grammar"]["features"]}
    # a vocative (set off by a comma) still allows the command
    r = ll.level_text("Andrés, mira por la ventana.")[0]
    assert "es.imperative.affirmative" in {f["id"] for f in r["grammar"]["features"]}


def test_clause_final_la_plus_verb_after_wh_word(ll):
    r = ll.level_text("¿Puedo saber por qué la busca?")[0]
    t = _tok(r, "busca")
    assert t["upos"] == "VERB" and t["headword"] == "buscar"
    # but an article + noun inside a longer clause stays a noun
    r = ll.level_text("Explicó que la reforma del código es necesaria.")[0]
    assert _tok(r, "reforma")["upos"] == "NOUN"


def test_question_inversion_before_a_name(ll):
    r = ll.level_text("¿Toca Lucas el piano?")[0]
    t = _tok(r, "Toca")
    assert t["upos"] == "VERB" and t["headword"] == "tocar" and "Mood=Ind" in t["feats"]
    assert "es.imperative.affirmative" not in {f["id"] for f in r["grammar"]["features"]}


def test_lower_case_word_is_not_a_name(ll):
    t = _tok(ll.level_text("Julia toca Bach y Chopin.")[0], "toca")
    assert t["upos"] == "VERB" and t["headword"] == "tocar"


def test_sentence_initial_word_after_inverted_punctuation(ll):
    t = _tok(ll.level_text("¡Silencio, Martín!")[0], "Silencio")
    assert t.get("headword") == "silencio"


def test_multi_word_place_name_is_not_counted(ll):
    t = _tok(ll.level_text("Buenos Aires es la capital.")[0], "Buenos")
    assert t.get("headword") is None and t.get("excluded")


def test_coordinated_verb_and_question_subject_are_not_commands(ll):
    for text, verb in [("Julia come pan, bebe leche y mira el mar.", "mira"),
                       ("¿Duerme Martín en la cocina?", "Duerme"), ("¿Qué mira Toby?", "mira")]:
        r = ll.level_text(text)[0]
        assert "Mood=Ind" in _tok(r, verb)["feats"], text
        assert "es.imperative.affirmative" not in {f["id"] for f in r["grammar"]["features"]}, text
    # a real command is still one
    assert "es.imperative.affirmative" in {f["id"] for f in ll.level_text("Come y mira.")[0]["grammar"]["features"]}


def test_lower_case_noun_after_names_is_counted(ll):
    t = _tok(ll.level_text("¿Come Ana pan?")[0], "pan")
    assert t["upos"] == "NOUN" and t["headword"] == "pan"
    # leche is also a form of the unlisted verb lechar: the listed noun wins
    t = _tok(ll.level_text("¿Bebe Ana leche?")[0], "leche")
    assert t["upos"] == "NOUN" and t["headword"] == "leche"

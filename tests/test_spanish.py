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

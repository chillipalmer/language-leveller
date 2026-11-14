"""Persian profile. The first tests need no parser model: they use hand-written CoNLL-U
in the annotation style of Stanza's PerDT model. The last runs the grammar self-tests
when Stanza's Persian models are installed."""

import os
from pathlib import Path

import pytest

from language_leveller.leveller import Leveller
from language_leveller.parsing import ConlluParser, parse_conllu

FA = Path(__file__).resolve().parent.parent / "languages" / "fa"

# "او به ایران رفته است." as Stanza (PerDT) parses it: verb lemma = past stem
PERFECT = """# text = او به ایران رفته است.
1\tاو\tاو\tPRON\t_\tNumber=Sing|Person=3|PronType=Prs\t4\tnsubj\t_\t_
2\tبه\tبه\tADP\t_\t_\t3\tcase\t_\t_
3\tایران\tایران\tPROPN\t_\tNumber=Sing\t4\tobl:arg\t_\t_
4\tرفته\tرفت\tVERB\t_\tNumber=Sing|Person=3|Tense=Past|VerbForm=Part|Voice=Act\t0\troot\t_\t_
5\tاست\tاست\tAUX\t_\tNumber=Sing|Person=3|Tense=Pres\t4\taux\t_\t_
6\t.\t.\tPUNCT\t_\t_\t4\tpunct\t_\t_
"""


@pytest.fixture(scope="module")
def ll():
    return Leveller.from_dir(FA, parser=ConlluParser())


def test_normalisation(ll):
    n = ll.cleaner.normalise
    zwnj = "‌"
    assert n("من کتاب می خوانم") == f"من کتاب می{zwnj}خوانم"
    assert n("او نمی رود") == f"او نمی{zwnj}رود"
    assert n("كتاب ها") == f"کتاب{zwnj}ها"            # Arabic kaf, spaced plural
    assert n("بزرگ تر") == f"بزرگ{zwnj}تر"
    assert n("دیده ام.") == f"دیده{zwnj}ام."
    assert n("سلامـــ") == "سلام"                      # tatweel
    assert n("میز") == "میز"                           # not a prefix


def test_verb_lemmas_reach_infinitives(ll):
    rec = ll.level_sentence(parse_conllu(PERFECT)[0])
    toks = {t["text"]: t for t in rec["tokens"]}
    assert toks["رفته"]["headword"] == "رفتن"
    assert toks["است"]["headword"] == "بودن"
    assert rec["grammar"]["level"] == "A2"
    assert [f["id"] for f in rec["grammar"]["features"]] == ["fa.perfect.present"]


# "شاید آنها کتاب را روی میز بگذارند." and "یکی از اولین کتاب‌هایشان کمی ..." in PerDT style:
# آنها, شان, یکی, اولین keep their own lemmas; most forms of گذاشتن get the present stem گذارد.
COMMON = """# text = شاید آنها کتاب را روی میز بگذارند.
1\tشاید\tشاید\tADV\t_\t_\t7\tadvmod\t_\t_
2\tآنها\tآنها\tPRON\t_\tNumber=Plur|Person=3|PronType=Prs\t7\tnsubj\t_\t_
3\tکتاب\tکتاب\tNOUN\t_\tNumber=Sing\t7\tobj\t_\t_
4\tرا\tرا\tADP\t_\t_\t3\tcase\t_\t_
5\tروی\tروی\tADP\t_\t_\t6\tcase\t_\t_
6\tمیز\tمیز\tNOUN\t_\tNumber=Sing\t7\tobl\t_\t_
7\tبگذارند\tگذارد\tVERB\t_\tMood=Sub|Number=Plur|Person=3|Tense=Pres\t0\troot\t_\t_
8\t.\t.\tPUNCT\t_\t_\t7\tpunct\t_\t_

# text = یکی از اولین کتاب‌هایشان کمی بود.
1\tیکی\tیکی\tNOUN\t_\tNumber=Sing\t6\tnsubj\t_\t_
2\tاز\tاز\tADP\t_\t_\t4\tcase\t_\t_
3\tاولین\tاولین\tADJ\t_\t_\t4\tamod\t_\t_
4-5\tکتاب‌هایشان\t_\t_\t_\t_\t_\t_\t_\t_
4\tکتاب‌های\tکتاب\tNOUN\t_\tNumber=Plur\t1\tnmod\t_\t_
5\tشان\tآنها\tPRON\t_\tNumber=Plur|Person=3|PronType=Prs\t4\tnmod:poss\t_\t_
6\tکمی\tکمی\tADV\t_\t_\t0\troot\t_\t_
7\tبود\tبود\tAUX\t_\tNumber=Sing|Person=3|Tense=Past\t6\tcop\t_\t_
8\t.\t.\tPUNCT\t_\t_\t6\tpunct\t_\t_
"""


def test_common_words_are_found(ll):
    heads = {}
    for s in parse_conllu(COMMON):
        rec = ll.level_sentence(s)
        assert "C2+" not in rec["vocab"]["level"], rec["vocab"]
        heads.update({t["text"]: t["headword"] for t in rec["tokens"] if "headword" in t})
    assert heads["شاید"] == "شاید"
    assert heads["آنها"] == heads["شان"] == "آن"
    assert heads["را"] == "را"
    assert heads["روی"] == "روی"
    assert heads["بگذارند"] == "گذاشتن"
    assert heads["یکی"] == "یک"
    assert heads["اولین"] == "اول"
    assert heads["کمی"] == "کمی"


# PerDT drops verb prefixes (برداشت -> داشت), keeps old stems (برساند -> رسانید) and
# variant spellings (مسأله) as lemmas.
PREFIXED = """# text = دیگران کتاب را برداشتند و برگشتند تا مسأله‌ها را به او برسانند و ببرند.
1\tدیگران\tدیگری\tNOUN\t_\tNumber=Plur\t4\tnsubj\t_\t_
2\tکتاب\tکتاب\tNOUN\t_\tNumber=Sing\t4\tobj\t_\t_
3\tرا\tرا\tADP\t_\t_\t2\tcase\t_\t_
4\tبرداشتند\tداشت\tVERB\t_\tNumber=Plur|Person=3|Tense=Past\t0\troot\t_\t_
5\tو\tو\tCCONJ\t_\t_\t6\tcc\t_\t_
6\tبرگشتند\tگشت\tVERB\t_\tNumber=Plur|Person=3|Tense=Past\t4\tconj\t_\t_
7\tتا\tتا\tSCONJ\t_\t_\t12\tmark\t_\t_
8\tمسأله‌ها\tمسأله\tNOUN\t_\tNumber=Plur\t12\tobj\t_\t_
9\tرا\tرا\tADP\t_\t_\t8\tcase\t_\t_
10\tبه\tبه\tADP\t_\t_\t11\tcase\t_\t_
11\tاو\tاو\tPRON\t_\tNumber=Sing|Person=3|PronType=Prs\t12\tobl\t_\t_
12\tبرسانند\tرسانید\tVERB\t_\tMood=Sub|Number=Plur|Person=3|Tense=Pres\t6\tadvcl\t_\t_
13\tو\tو\tCCONJ\t_\t_\t14\tcc\t_\t_
14\tببرند\tبرد\tVERB\t_\tMood=Sub|Number=Plur|Person=3|Tense=Pres\t12\tconj\t_\t_
15\t.\t.\tPUNCT\t_\t_\t4\tpunct\t_\t_
"""


def test_prefixed_verbs_stems_and_variant_lemmas(ll):
    rec = ll.level_sentence(parse_conllu(PREFIXED)[0])
    heads = {t["text"]: t["headword"] for t in rec["tokens"] if "headword" in t}
    assert heads["دیگران"] == "دیگر"
    assert heads["برداشتند"] == "برداشتن"     # not داشتن (have)
    assert heads["برگشتند"] == "برگشتن"       # not گشتن (wander)
    assert heads["مسأله‌ها"] == "مسئله"        # lemma is a listed variant spelling
    assert heads["برسانند"] == "رساندن"       # ب + رسان, not a بر- verb
    assert heads["ببرند"] == "بردن"


ADDED = """# text = متأسفانه شرایط و اطلاعات نزد همگان باران را برانگیخت.
1\tمتأسفانه\tمتأسفانه\tADV\t_\t_\t9\tadvmod\t_\t_
2\tشرایط\tشرایط\tNOUN\t_\tNumber=Plur\t9\tnsubj\t_\t_
3\tو\tو\tCCONJ\t_\t_\t4\tcc\t_\t_
4\tاطلاعات\tاطلاعات\tNOUN\t_\tNumber=Plur\t2\tconj\t_\t_
5\tنزد\tنزد\tADP\t_\t_\t6\tcase\t_\t_
6\tهمگان\tهمگان\tNOUN\t_\tNumber=Plur\t2\tnmod\t_\t_
7\tباران\tباران\tNOUN\t_\tNumber=Sing\t9\tobj\t_\t_
8\tرا\tرا\tADP\t_\t_\t7\tcase\t_\t_
9\tبرانگیخت\tانگیخت\tVERB\t_\tNumber=Sing|Person=3|Tense=Past\t0\troot\t_\t_
10\t.\t.\tPUNCT\t_\t_\t9\tpunct\t_\t_
"""


def test_added_words_and_plurals(ll):
    rec = ll.level_sentence(parse_conllu(ADDED)[0])
    heads = {t["text"]: t["headword"] for t in rec["tokens"] if "headword" in t}
    assert heads == {"متأسفانه": "متأسفانه", "شرایط": "شرط", "و": "و", "اطلاعات": "اطلاع",
                     "نزد": "نزد", "همگان": "همه", "باران": "باران", "را": "را",
                     "برانگیخت": "برانگیختن"}


def test_grammar_patterns_compile(ll):
    s = parse_conllu(PERFECT)[0]
    for f in ll.grammar.features:
        f.find(s)                                       # raises on a bad pattern or regex


def _stanza_fa_installed() -> bool:
    try:
        import stanza  # noqa: F401
    except ImportError:
        return False
    root = Path(os.environ.get("STANZA_RESOURCES_DIR", Path.home() / "stanza_resources"))
    return (root / "resources.json").exists() and (root / "fa").is_dir()


@pytest.mark.skipif(not _stanza_fa_installed(), reason="Stanza Persian models not installed")
def test_grammar_self_tests_with_stanza():
    full = Leveller.from_dir(FA)
    bad = [r for r in full.test_grammar() if not r["ok"]]
    assert not bad, bad

#!/usr/bin/env python3
"""Build a UD-tagged morphology lexicon (morph.tsv.gz) for Language Leveller.

Columns: form  lemma  upos  feats      (feats in UD format, e.g. Mood=Sub|Tense=Pres)

Sources (combine any):
  --unimorph FILE   UniMorph data file (https://github.com/unimorph/<iso3>), any language
  --verbecc LANG    conjugate verbs with verbecc (pip install verbecc); Spanish mapping included
  --vocab FILE      your frequency list; with --verbecc, every verb in it is conjugated

Example (Spanish):
  python tools/build_morph.py --unimorph spa/spa --verbecc es \
      --vocab languages/es/vocab.tsv --vocab-pos v --out languages/es/morph.tsv.gz
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import sys

# ---------------------------------------------------------------- UniMorph -> UD
UM_POS = {"V": "VERB", "N": "NOUN", "ADJ": "ADJ", "ADV": "ADV", "V.PTCP": "VERB"}


def unimorph_to_ud(tags: str) -> tuple[str, str] | None:
    parts = tags.split(";")
    if "PRO" in parts:                       # verb + enclitic: keep the verb's own features
        parts = parts[:parts.index("PRO") - 1]   # drop "ACC;PRO;3;SG" etc.
        if parts == ["V"]:                   # bare infinitive + clitic (decirlo)
            parts = ["V", "NFIN"]
    p = set(parts)
    upos = UM_POS.get(parts[0])
    if not upos:
        return None
    f: dict[str, str] = {}
    if upos == "VERB":
        if "NFIN" in p:
            f["VerbForm"] = "Inf"
        elif "V.CVB" in p:
            f["VerbForm"] = "Ger"
        elif "V.PTCP" in p:
            f.update(VerbForm="Part", Tense="Past")
        else:
            f["VerbForm"] = "Fin"
            if "NEG" in p and "IMP" in p:     # UD tags negative imperatives as subjunctive
                f.update(Mood="Sub", Tense="Pres")
            elif "IMP" in p:
                f["Mood"] = "Imp"
            elif "SBJV" in p:
                f["Mood"] = "Sub"
            elif "COND" in p:
                f["Mood"] = "Cnd"
            elif "IND" in p:
                f["Mood"] = "Ind"
            if "Tense" not in f and "Mood" in f and f["Mood"] not in ("Imp", "Cnd"):
                if "PRS" in p:
                    f["Tense"] = "Pres"
                elif "FUT" in p:
                    f["Tense"] = "Fut"
                elif "PST" in p:
                    f["Tense"] = "Imp" if ("IPFV" in p or f["Mood"] == "Sub") else "Past"
            if True:
                if "1" in p: f["Person"] = "1"
                elif "3" in p or "FORM" in p: f["Person"] = "3"   # usted forms are 3rd person in UD
                elif "2" in p: f["Person"] = "2"
    if "SG" in p: f["Number"] = "Sing"
    elif "PL" in p: f["Number"] = "Plur"
    if "MASC" in p: f["Gender"] = "Masc"
    elif "FEM" in p: f["Gender"] = "Fem"
    if " " in tags:
        return None
    return upos, "|".join(f"{k}={v}" for k, v in sorted(f.items()))


def read_unimorph(path: str):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3 or " " in cols[1]:   # skip multiword forms ("no ores")
                continue
            res = unimorph_to_ud(cols[2])
            if res:
                yield cols[1], cols[0], res[0], res[1]


# ---------------------------------------------------------------- verbecc (Spanish)
ES_TENSES = {
    ("indicativo", "presente"): "Mood=Ind|Tense=Pres",
    ("indicativo", "pretérito-imperfecto"): "Mood=Ind|Tense=Imp",
    ("indicativo", "pretérito-perfecto-simple"): "Mood=Ind|Tense=Past",
    ("indicativo", "futuro"): "Mood=Ind|Tense=Fut",
    ("condicional", "presente"): "Mood=Cnd",
    ("subjuntivo", "presente"): "Mood=Sub|Tense=Pres",
    ("subjuntivo", "pretérito-imperfecto-1"): "Mood=Sub|Tense=Imp",
    ("subjuntivo", "pretérito-imperfecto-2"): "Mood=Sub|Tense=Imp",
    ("subjuntivo", "futuro"): "Mood=Sub|Tense=Fut",
    ("imperativo", "afirmativo"): "Mood=Imp",
    ("imperativo", "negativo"): "Mood=Sub|Tense=Pres",
}


def read_verbecc(lang: str, verbs):
    if lang != "es":
        sys.exit("verbecc mapping is only defined for Spanish so far; add one to ES_TENSES' sibling")
    logging.disable(logging.CRITICAL)
    from verbecc import CompleteConjugator
    cg = CompleteConjugator(lang=lang)
    for v in verbs:
        try:
            d = json.loads(str(cg.conjugate(v)))
        except Exception as e:
            print(f"verbecc: skipped {v}: {e}", file=sys.stderr)
            continue
        m = d["moods"]
        yield v, v, "VERB", "VerbForm=Inf"
        for g in m.get("gerundio", {}).get("gerundio", []):
            yield _form(g), v, "VERB", "VerbForm=Ger"
        for p in m.get("participo", {}).get("participo", []):
            base = _form(p)
            yield base, v, "VERB", "Gender=Masc|Number=Sing|Tense=Past|VerbForm=Part"
            if base.endswith("o"):
                stem = base[:-1]
                for suf, g, n in (("a", "Fem", "Sing"), ("os", "Masc", "Plur"), ("as", "Fem", "Plur")):
                    yield stem + suf, v, "VERB", f"Gender={g}|Number={n}|Tense=Past|VerbForm=Part"
        for (mood, tense), feats in ES_TENSES.items():
            for row in m.get(mood, {}).get(tense, []):
                if not isinstance(row, dict):
                    continue
                person = row.get("p")
                num = {"s": "Sing", "p": "Plur"}.get(row.get("n"))
                f = dict(x.split("=") for x in feats.split("|"))
                f["VerbForm"] = "Fin"
                if person:
                    f["Person"] = person
                if num:
                    f["Number"] = num
                for c in row.get("c", []):
                    yield _form(c), v, "VERB", "|".join(f"{k}={x}" for k, x in sorted(f.items()))


def _form(x) -> str:
    s = x["c"][0] if isinstance(x, dict) else x
    return s.split()[-1]            # drop subject pronoun / "no"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unimorph")
    ap.add_argument("--verbecc")
    ap.add_argument("--vocab")
    ap.add_argument("--vocab-pos", default="v", help="POS code(s) marking verbs in the vocab list, comma-separated")
    ap.add_argument("--extra-verbs", default="", help="comma-separated extra verbs to conjugate")
    ap.add_argument("--keep-all", action="store_true",
                    help="keep every row; default keeps verb rows plus non-verb rows whose "
                         "form is also a verb form (all the corrector needs)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    rows: set[tuple[str, str, str, str]] = set()
    vocab_words: set[str] = set()
    if a.vocab:
        dialect = "excel-tab" if a.vocab.endswith((".tsv", ".txt")) else "excel"
        with open(a.vocab, encoding="utf-8-sig") as fh:
            vocab_words = {(r.get("word") or "").strip() for r in csv.DictReader(fh, dialect=dialect)}
    if a.unimorph:
        rows.update(read_unimorph(a.unimorph))
        print(f"unimorph: {len(rows)} rows", file=sys.stderr)
    if a.verbecc:
        verbs = set(v for v in a.extra_verbs.split(",") if v)
        if a.vocab:
            vp = set(a.vocab_pos.split(","))
            dialect = "excel-tab" if a.vocab.endswith((".tsv", ".txt")) else "excel"
            with open(a.vocab, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh, dialect=dialect):
                    r = {k.strip().lower(): (v or "").strip() for k, v in r.items()}
                    if r.get("pos") in vp and r.get("word"):
                        verbs.add(r["word"])
        n0 = len(rows)
        rows.update(read_verbecc(a.verbecc, sorted(verbs)))
        print(f"verbecc: {len(verbs)} verbs, +{len(rows) - n0} rows", file=sys.stderr)

    if not a.keep_all:
        # keep: verb rows; non-verb rows whose form is also a verb form (ambiguity);
        # non-verb rows whose lemma is in the vocab list (lemma lookup for inflected
        # nouns/adjectives the parser fails to lemmatise)
        verb_forms = {r[0].lower() for r in rows if r[2] == "VERB"}
        rows = {r for r in rows if r[2] == "VERB" or r[0].lower() in verb_forms
                or r[1] in vocab_words}
    op = gzip.open if a.out.endswith(".gz") else open
    with op(a.out, "wt", encoding="utf-8", newline="") as fh:
        fh.write("form\tlemma\tupos\tfeats\n")
        for r in sorted(rows):
            fh.write("\t".join(r) + "\n")
    print(f"wrote {len(rows)} rows to {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

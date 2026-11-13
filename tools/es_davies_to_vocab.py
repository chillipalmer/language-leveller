#!/usr/bin/env python3
"""Convert a Davies-style Spanish list (rank, word, pos [, ...]) to an LL vocab file.

Keeps only facts: id, rank, word, pos (Universal POS), feats (noun gender), variants
(apocopated and inflected forms of closed-class words). Glosses, sentences, frequency
and dispersion figures are dropped.

  python tools/es_davies_to_vocab.py davies.csv languages/es/vocab.tsv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Davies POS code -> (UPOS, feats)
POS = {
    "v": ("VERB", ""),
    "nm": ("NOUN", "Gender=Masc"),
    "nf": ("NOUN", "Gender=Fem"),
    "nm/f": ("NOUN", "Gender=Masc,Fem"),       # m. with a separate f. form (autor/autora)
    "nc": ("NOUN", "Gender=Com"),              # same form for both (estudiante)
    "nmf": ("NOUN", "Gender=Masc,Fem"),        # gender changes meaning (el/la capital)
    "n": ("NOUN", ""),
    "adj": ("ADJ", ""),
    "adv": ("ADV", ""),
    "pron": ("PRON", ""),
    "num": ("NUM", ""),
    "prep": ("ADP", ""),
    "art": ("DET", "PronType=Art"),
    "interj": ("INTJ", ""),
}
# Davies' single "conj" class, split by hand
CCONJ = {"y", "o", "pero", "ni", "sino", "mas"}
# Davies lists these as adjectives; UD treats them as determiners
DETERMINERS = {"su", "todo", "este", "otro", "ese", "mucho", "mi", "alguno", "mismo", "poco",
               "tanto", "nuestro", "cada", "aquel", "cierto", "ninguno", "cualquier", "varios",
               "demasiado", "tu", "ambos", "vuestro", "suyo", "mío", "tuyo", "bastante",
               "cuanto", "tal", "semejante"}
# forms a lemmatiser may not map back (apocope, plural/feminine pronouns, article forms)
VARIANTS = {
    ("el", "DET"): "la|los|las", ("un", "DET"): "una|unos|unas",
    ("él", "PRON"): "ellos", ("ella", "PRON"): "ellas",
    ("nosotros", "PRON"): "nosotras", ("vosotros", "PRON"): "vosotras",
    ("éste", "PRON"): "ésta|éstos|éstas", ("ése", "PRON"): "ésa|ésos|ésas",
    ("aquél", "PRON"): "aquélla|aquéllos|aquéllas",
    ("le", "PRON"): "les", ("lo", "PRON"): "los", ("la", "PRON"): "las",
    ("este", "DET"): "esta|estos|estas", ("ese", "DET"): "esa|esos|esas",
    ("aquel", "DET"): "aquella|aquellos|aquellas",
    ("su", "DET"): "sus", ("mi", "DET"): "mis", ("tu", "DET"): "tus",
    ("alguno", "DET"): "algún|alguna|algunos|algunas",
    ("ninguno", "DET"): "ningún|ninguna|ningunos|ningunas",
    ("cualquier", "DET"): "cualquiera|cualesquiera",
    ("grande", "ADJ"): "gran", ("bueno", "ADJ"): "buen", ("malo", "ADJ"): "mal",
    ("primero", "ADJ"): "primer", ("tercero", "ADJ"): "tercer",
    ("ciento", "NUM"): "cien", ("uno", "NUM"): "una|un", ("quien", "PRON"): "quienes",
    ("quién", "PRON"): "quiénes", ("cual", "PRON"): "cuales", ("cuál", "PRON"): "cuáles",
    ("santo", "ADJ"): "san",
    ("a", "ADP"): "al", ("de", "ADP"): "del",          # contractions spaCy leaves unsplit
    ("y", "CCONJ"): "e", ("o", "CCONJ"): "u",          # before i-/hi- and o-/ho-
    ("quizás", "ADV"): "quizá",
}


def feminine(word: str) -> str | None:
    """autor -> autora, médico -> médica, bailarín -> bailarina."""
    if word.endswith("o"):
        return word[:-1] + "a"
    if word.endswith(("or", "ón")):
        return word + "a" if word.endswith("or") else word[:-2] + "ona"
    if word.endswith("ín"):
        return word[:-2] + "ina"
    return None


def main():
    src, dst = sys.argv[1], sys.argv[2]
    text = Path(src).read_text(encoding="utf-8-sig")
    dialect = "excel-tab" if src.endswith((".tsv", ".txt")) else "excel"
    rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    out, ids, unknown = [], set(), set()
    for r in rows:
        rank, word, pos = int(r["rank"]), r["word"].strip(), r["pos"].strip()
        variants = []
        if ", " in word:                       # "el, la"
            word, *rest = [w.strip() for w in word.split(",")]
            variants += rest
        if pos == "conj":
            upos, feats = ("CCONJ" if word in CCONJ else "SCONJ"), ""
        elif pos == "adj" and word in DETERMINERS:
            upos, feats = "DET", ""
        elif pos in POS:
            upos, feats = POS[pos]
        else:
            unknown.add(pos)
            continue
        if pos == "nm/f" and feminine(word):
            variants.append(feminine(word))
        variants += VARIANTS.get((word, upos), "").split("|")
        variants = list(dict.fromkeys(v for v in variants if v and v != word))
        base = f"{word}_{upos}"
        uid, n = base, 2
        while uid in ids:
            uid, n = f"{base}{n}", n + 1
        ids.add(uid)
        out.append([uid, rank, word, upos, feats, "|".join(variants)])
    if unknown:
        sys.exit(f"unknown POS codes: {sorted(unknown)}")
    with open(dst, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, dialect="excel-tab")
        w.writerow(["id", "rank", "word", "pos", "feats", "variants"])
        w.writerows(sorted(out, key=lambda x: x[1]))
    print(f"wrote {len(out)} entries to {dst}", file=sys.stderr)


if __name__ == "__main__":
    main()

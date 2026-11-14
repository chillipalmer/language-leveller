"""Check the Persian grammar profile against the UD Persian-PerDT treebank.

The treebank's MISC column keeps each verb's past#present stems (OrigLemma=کرد#کن).
From them this script derives a gold analysis for every finite verb: simple past,
past imperfective, present subjunctive, present indicative, imperative or participle.
It then runs the raw sentence text through LL (parser, normalisation, grammar) and
scores three features token by token:

  fa.past.imperfective                  vs gold past imperfective
  fa.subj.modal + fa.subj.present       vs gold present subjunctive (the verb itself)
  fa.past.simple                        vs gold simple past

Gold "simple past" includes the main verb of the future (خواهد رفت) and short
infinitives (باید رفت), which are past-stem forms LL rightly does not count as simple
past, so simple-past recall is understated. Feature hit counts and the distribution of
sentence grammar levels are printed too.

    git clone --depth 1 https://github.com/UniversalDependencies/UD_Persian-PerDT
    python tools/fa_eval_perdt.py UD_Persian-PerDT/fa_perdt-ud-dev.conllu
"""

from __future__ import annotations

import argparse
import collections
import difflib
import re
import sys
import time
from pathlib import Path

from language_leveller.leveller import Leveller

ZWNJ = "‌"
PREVERBS = ["بر", "در", "باز", "فرو", "فرا", "وا", "ور"]
ENDINGS = ["", "م", "ی", "د", "یم", "ید", "ند"]
PART_ENDINGS = ["ه", "هام", "های", "هایم", "هاید", "هاند"]
SCORED = {"fa.past.imperfective": "impf", "fa.subj.modal": "subj",
          "fa.subj.present": "subj", "fa.past.simple": "past"}


def read_treebank(path: Path) -> list[dict]:
    sents, cur = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# text ="):
            cur = {"text": line.split("=", 1)[1].strip(), "words": []}
            sents.append(cur)
        elif line[:1].isdigit() and cur is not None:
            c = line.split("\t")
            if "-" in c[0] or "." in c[0]:
                continue
            misc = dict(kv.split("=", 1) for kv in c[9].split("|") if "=" in kv)
            cur["words"].append({"form": c[1], "upos": c[3], "feats": c[5],
                                 "stems": misc.get("OrigLemma", "")})
    return sents


def gold_class(w: dict) -> str | None:
    """Gold verb analysis from past#present stems; None when ambiguous or not a verb."""
    if w["upos"] != "VERB" or "#" not in w["stems"]:
        return None
    if "Mood=Imp" in w["feats"]:
        return "imp"
    past, pres = w["stems"].split("#")
    f = w["form"].replace(ZWNJ, "")
    found = set()
    for stem, kind in ((past, "P"), (pres, "R")):
        if not stem:
            continue
        splits = [("", stem)] + [(p, stem[len(p):]) for p in PREVERBS
                                 if stem.startswith(p) and len(stem) > len(p) + 1]
        for pv, core in splits:
            for neg in ("", "ن"):
                for asp in ("", "می", "ب", "بی"):
                    if asp.startswith("ب") and neg:
                        continue
                    for e in ENDINGS + PART_ENDINGS:
                        if f == pv + neg + asp + core + e:
                            found.add((kind, asp, e))
    cls = set()
    for kind, asp, e in found:
        if kind == "P" and e.startswith("ه"):
            cls.add("part")
        elif kind == "P":
            cls.add({"می": "impf", "": "past"}.get(asp, "literary_past"))
        elif asp == "می" or past in ("داشت", "هست"):
            cls.add("pres")
        elif e == "":
            cls.add("imp")
        else:
            cls.add("subj")
    return cls.pop() if len(cls) == 1 else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("conllu", type=Path, help="PerDT .conllu file (dev or test)")
    ap.add_argument("--lang", default=str(Path(__file__).resolve().parent.parent / "languages" / "fa"))
    ap.add_argument("--parser", help="parser spec, e.g. stanza:fa (default: config.yaml)")
    ap.add_argument("--limit", type=int, help="only the first N sentences")
    ap.add_argument("--examples", type=int, default=10, help="errors to print per class")
    a = ap.parse_args(argv)

    ll = Leveller.from_dir(a.lang, parser=a.parser)
    sents = read_treebank(a.conllu)[: a.limit]
    t0 = time.time()
    tp, fp, fn = collections.Counter(), collections.Counter(), collections.Counter()
    errors = collections.defaultdict(list)
    hits, levels = collections.Counter(), collections.Counter()
    for s in sents:
        recs = ll.level_text(s["text"])
        toks, pred = [], collections.defaultdict(set)
        for r in recs:
            base = len(toks)
            toks += [t["text"] for t in r["tokens"]]
            levels[r["grammar"]["level"]] += 1
            for f in r["grammar"]["features"]:
                hits[f["id"]] += len(f["tokens"])
                if f["id"] in SCORED:
                    for group in f["tokens"]:
                        for i in group:
                            pred[base + i].add(SCORED[f["id"]])
        gold = [w["form"] for w in s["words"]]
        sm = difflib.SequenceMatcher(a=gold, b=toks, autojunk=False)
        align = {a_ + k: b + k for a_, b, n in sm.get_matching_blocks() for k in range(n)}
        for gi, w in enumerate(s["words"]):
            g = gold_class(w)
            if gi not in align or g is None:
                continue
            p = pred.get(align[gi], set())
            for cls in ("impf", "subj", "past"):
                if g == cls and cls in p:
                    tp[cls] += 1
                elif g == cls:
                    fn[cls] += 1
                    errors[cls, "missed"].append((w["form"], s["text"]))
                elif cls in p:
                    fp[cls] += 1
                    errors[cls, f"wrong (gold {g})"].append((w["form"], s["text"]))

    print(f"{len(sents)} sentences in {time.time() - t0:.0f} s\n")
    names = {"impf": "past imperfective", "subj": "present subjunctive", "past": "simple past"}
    for cls, name in names.items():
        p = tp[cls] / (tp[cls] + fp[cls]) if tp[cls] + fp[cls] else 0.0
        r = tp[cls] / (tp[cls] + fn[cls]) if tp[cls] + fn[cls] else 0.0
        print(f"{name:<20} precision {p:.3f}  recall {r:.3f}  (tp {tp[cls]}, fp {fp[cls]}, fn {fn[cls]})")
    print("\nsentence grammar levels: " + ", ".join(f"{k} {v}" for k, v in sorted(levels.items())))
    print("\nfeature hits:")
    for f in ll.grammar.features:
        print(f"  {f.id:<36} {f.level:<3} {hits.get(f.id, 0)}")
    if a.examples:
        for (cls, kind), lst in sorted(errors.items()):
            print(f"\n{names[cls]}, {kind}:")
            for form, text in lst[: a.examples]:
                print(f"  {form:<14} {text[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

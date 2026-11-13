"""Command-line entry point.

  leveller level   --lang languages/es  input.txt  [--vocab F] [--grammar F] [--format jsonl|json|tsv]
  leveller explain --lang languages/es  "Si lo hubiera sabido, no habría venido."
  leveller test-grammar --lang languages/es
  leveller parse   --lang languages/es  "text"      (dump the UD parse, for writing patterns)
"""

from __future__ import annotations

import argparse
import json
import sys

from .leveller import Leveller


def _build(a) -> Leveller:
    return Leveller.from_dir(a.lang, vocab_path=a.vocab, grammar_path=a.grammar,
                             parser=a.parser,
                             morph_path=False if a.no_morph else a.morph,
                             bands=_bands(a.bands))


def _bands(spec):
    """'A1=600,A2=1200,B1=2000' -> {'A1': 600, ...}"""
    if not spec:
        return None
    return {k.strip(): int(v) for k, v in (p.split("=") for p in spec.split(","))}


def _read(a) -> str:
    if a.input in (None, "-"):
        return sys.stdin.read()
    if a.text:
        return a.input
    with open(a.input, encoding="utf-8") as fh:
        return fh.read()


def cmd_level(a):
    ll = _build(a)
    recs = ll.level_text(_read(a), fmt=a.input_format)
    out = sys.stdout
    if a.format == "json":
        json.dump(recs, out, ensure_ascii=False, indent=2)
        out.write("\n")
    elif a.format == "jsonl":
        for r in recs:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:  # tsv summary
        out.write("level\tvocab_level\tgrammar_level\tmax_rank\tcoverage\tfeatures\tflags\ttext\n")
        for r in recs:
            feats = ",".join(f"{f['id']}({f['level']})" for f in r["grammar"]["features"])
            out.write("\t".join(str(x) for x in (
                r["level"], r["vocab"]["level"], r["grammar"]["level"],
                r["vocab"]["max_rank"] or "", r["vocab"]["coverage"] or "",
                feats, ",".join(r["flags"]), r["text"])) + "\n")


def cmd_explain(a):
    ll = _build(a)
    for r in ll.level_text(_read(a), fmt=a.input_format):
        print(f"\n{r['text']}")
        print(f"  LEVEL {r['level']}   vocab {r['vocab']['level']}   grammar {r['grammar']['level']}"
              + (f"   flags: {', '.join(r['flags'])}" if r["flags"] else ""))
        for t in r["tokens"]:
            if "excluded" in t:
                print(f"    {t['text']:<16} —  ({t['excluded']})")
            else:
                hw = t.get("headword", "")
                fix = f"   [fixed: {t['morph_fix']}]" if t.get("morph_fix") else ""
                print(f"    {t['text']:<16} {str(t['rank']):>6}  {t['level']:<4} "
                      f"{hw:<14} {t.get('match', '')}{fix}")
        for f in r["grammar"]["features"]:
            print(f"    [{f['level']}] {f['label']}  ({f['id']})")
        ign = r.get("source", {}).get("ignored")
        if ign:
            print("    ignored: " + ", ".join(f"{i['type']}:{i['text']}" for i in ign))


def cmd_test_grammar(a):
    ll = _build(a)
    res = ll.test_grammar()
    bad = [r for r in res if not r["ok"]]
    for r in bad:
        exp = "should match" if r["kind"] == "pos" else "should NOT match"
        print(f"FAIL {r['feature']}: {exp}: {r['text']}")
    print(f"\n{len(res) - len(bad)}/{len(res)} grammar tests passed")
    sys.exit(1 if bad else 0)


def cmd_parse(a):
    ll = _build(a)
    for s in ll.parser.parse(_read(a)):
        print(f"# {s.text}")
        for t in s.tokens:
            feats = "|".join(f"{k}={v}" for k, v in sorted(t.feats.items())) or "_"
            print(f"{t.i}\t{t.text}\t{t.lemma}\t{t.upos}\t{feats}\t{t.head}\t{t.rel}")
        print()


def main(argv=None):
    p = argparse.ArgumentParser(prog="leveller", description="Language Leveller")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("level", cmd_level), ("explain", cmd_explain),
                     ("test-grammar", cmd_test_grammar), ("parse", cmd_parse)):
        sp = sub.add_parser(name)
        sp.add_argument("--lang", required=True, help="language directory (contains config.yaml)")
        sp.add_argument("--vocab", help="override vocabulary file")
        sp.add_argument("--grammar", help="override grammar file")
        sp.add_argument("--parser", help="override parser, e.g. spacy:es_core_news_lg")
        sp.add_argument("--morph", help="override morphology lexicon file")
        sp.add_argument("--no-morph", action="store_true", help="disable morphology correction")
        sp.add_argument("--bands", help="override vocab cutoffs, e.g. A1=600,A2=1200,B1=2000,B2=3000,C1=4000,C2=5000")
        if name != "test-grammar":
            sp.add_argument("input", nargs="?", help="file path, '-' for stdin, or text with -t")
            sp.add_argument("-t", "--text", action="store_true", help="treat input as literal text")
            sp.add_argument("--input-format", default="auto",
                            choices=["auto", "text", "html", "markdown"])
        if name == "level":
            sp.add_argument("--format", default="jsonl", choices=["jsonl", "json", "tsv"])
        sp.set_defaults(fn=fn)
    a = p.parse_args(argv)
    if a.cmd in ("explain", "parse") and a.input and not a.text:
        import os
        a.text = not os.path.exists(a.input)
    a.fn(a)


if __name__ == "__main__":
    main()

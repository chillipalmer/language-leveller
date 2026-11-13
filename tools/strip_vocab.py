#!/usr/bin/env python3
"""Reduce a frequency list to facts only, for publishing.

Keeps: rank, word, pos (plus level / variants / translit if you created them yourself).
Drops: glosses, example sentences, translations, and any other column.

  python tools/strip_vocab.py davies_full.csv languages/es/vocab.tsv
  python tools/strip_vocab.py in.xlsx out.tsv --keep rank,word,pos --rename lemma=word

Input: .csv, .tsv or .xlsx (first sheet). Output: TSV.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

DEFAULT_KEEP = ["rank", "word", "pos", "level", "variants", "translit"]


def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        ws = load_workbook(path, read_only=True, data_only=True).worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = [str(h or "").strip() for h in next(it)]
        return [dict(zip(header, ["" if v is None else str(v) for v in row])) for row in it]
    text = path.read_text(encoding="utf-8-sig")
    dialect = "excel-tab" if path.suffix.lower() in (".tsv", ".txt", ".tab") else "excel"
    return list(csv.DictReader(text.splitlines(), dialect=dialect))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--keep", default=",".join(DEFAULT_KEEP),
                    help="columns to keep, in output order (default: %(default)s)")
    ap.add_argument("--rename", default="",
                    help="map source column names to LL names, e.g. 'lemma=word,freq_rank=rank'")
    a = ap.parse_args()

    rename = dict(p.split("=", 1) for p in a.rename.split(",") if "=" in p)
    keep = [k.strip().lower() for k in a.keep.split(",") if k.strip()]
    rows = read_rows(Path(a.src))
    if not rows:
        sys.exit("no rows")

    def norm(k):
        k = (k or "").strip()
        return rename.get(k, rename.get(k.lower(), k)).lower()

    src_cols = {norm(k): k for k in rows[0]}
    missing = [c for c in ("rank", "word", "pos") if c not in src_cols]
    if missing:
        sys.exit(f"missing required column(s) {missing}; found {list(rows[0])}. Use --rename.")
    out_cols = [c for c in keep if c in src_cols]
    dropped = [k for k in rows[0] if norm(k) not in out_cols]

    with open(a.dst, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, dialect="excel-tab")
        w.writerow(out_cols)
        n = 0
        for r in rows:
            vals = [(r.get(src_cols[c]) or "").strip() for c in out_cols]
            if vals[out_cols.index("rank")] and vals[out_cols.index("word")]:
                w.writerow(vals)
                n += 1
    print(f"wrote {n} rows, columns {out_cols}; dropped {dropped}", file=sys.stderr)


if __name__ == "__main__":
    main()

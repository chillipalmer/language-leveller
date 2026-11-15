"""Convert Persian transliteration from the IPA-style spelling (æ ɑ ʃ ʧ ʤ x ɣ j ʔ)
to the project scheme (a ā š č j x q ġ y '), using the Persian word to tell ق (q) from
غ (ġ) and to add the h of a final silent ه (-eh).

    python tools/fa_translit_convert.py languages/fa/vocab.tsv      # rewrites in place

convert(word, ipa) is importable for other text (e.g. story transliterations).
"""
import csv
import re
import sys

SIMPLE = [("ɡ", "g"), ("j", "y"), ("ʤ", "j"), ("ʧ", "č"), ("ʃ", "š"), ("ʒ", "ž"),
          ("æ", "a"), ("ɑ", "ā"), ("ʔ", "'")]
ALLOWED = re.compile(r"^[a-zāčšžġ' /-]*$")
ZWNJ = "‌"

# ZWNJ compounds whose first part ends in silent ه: the source spelling fuses the parts,
# so they are given by hand (hyphen at the ZWNJ, -eh before it).
HAND = {
    "سرمایه‌گذاری": "sarmāyeh-gozāri", "سرمایه‌گذار": "sarmāyeh-gozār",
    "سرمایه‌داری": "sarmāyeh-dāri", "برنامه‌ریزی": "barnāmeh-rizi",
    "بهره‌برداری": "bahreh-bardāri", "بهره‌گیری": "bahreh-giri", "بهره‌وری": "bahreh-vari",
    "منطقه‌ای": "mantaqeh-i", "حرفه‌ای": "herfeh-i", "هسته‌ای": "hasteh-i",
    "رسانه‌ای": "resāneh-i", "رایانه‌ای": "rāyāneh-i", "شیشه‌ای": "šišeh-i",
    "خامنه‌ای": "xāmeneh-i", "سه‌شنبه": "seh-šambeh", "صرفه‌جویی": "sarfeh-juyi",
    "روزنامه‌نگار": "ruznāmeh-negār", "کناره‌گیری": "kenāreh-giri",
    "کره‌جنوبی": "koreh-ye jonubi", "هفته‌نامه": "hafteh-nāmeh",
}


def _uvulars(word: str, ipa: str) -> str:
    """ɣ -> q for ق, ġ for غ, in order; a doubled ɣɣ is one written letter."""
    letters = re.findall("[قغ]", word)
    runs = re.findall("ɣ+", ipa)
    if len(letters) != len(runs):
        raise ValueError(f"cannot align ق/غ in {word!r} / {ipa!r}")
    it = iter(letters)
    return re.sub("ɣ+", lambda m: ("q" if next(it) == "ق" else "ġ") * len(m.group()), ipa)


def _final_h(word_tok: str, tr_tok: str) -> str:
    """Silent final ه is written -eh (-eh-ye before a fused ezafe)."""
    if not word_tok.endswith("ه") or tr_tok.endswith("h"):   # pronounced h: rāh, movājeh
        return tr_tok
    if tr_tok.endswith("eye"):               # fused ezafe: namāyandeye -> namāyandeh-ye
        return tr_tok[:-3] + "eh-ye"
    if tr_tok.endswith("e"):
        return tr_tok + "h"
    return tr_tok


def convert(word: str, ipa: str) -> str:
    if not ipa:
        return ipa
    if word in HAND:
        return HAND[word]
    out = []
    for alt in ipa.split(" / "):
        t = _uvulars(word, alt)
        for a, b in SIMPLE:
            t = t.replace(a, b)
        w_toks, t_toks = word.split(), t.split()
        if len(w_toks) == len(t_toks):
            t_toks = [_final_h(w.split(ZWNJ)[-1], x) for w, x in zip(w_toks, t_toks)]
        else:                                # spacing differs: only the last word is safe
            t_toks[-1] = _final_h(w_toks[-1].split(ZWNJ)[-1], t_toks[-1])
        t = " ".join(t_toks)
        if not ALLOWED.match(t):
            raise ValueError(f"unconverted symbol in {word!r}: {t!r}")
        out.append(t)
    return " / ".join(out)


def main(path: str) -> None:
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    head = lines[0].split("\t")
    wi, ti = head.index("word"), head.index("translit")
    for i, line in enumerate(lines[1:], 1):
        if not line:
            continue
        c = line.split("\t")
        c[ti] = convert(c[wi], c[ti])
        lines[i] = "\t".join(c)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])

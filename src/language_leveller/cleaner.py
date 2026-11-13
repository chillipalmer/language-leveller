"""Text intake: turn arbitrary input (plain text, HTML, Markdown, social-media posts)
into clean segments for the parser, recording everything that was removed.

Language-neutral rules live here; language-specific lists (abbreviations,
laughter patterns) come from the language config's `cleaning:` section.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Callable

from .model import Segment

URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w.-]+\.(?:com|org|net|es|io|co|uk|au|de|fr)(?:/\S*)?\b", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
MENTION = re.compile(r"(?<!\w)@\w+")
HASHTAG = re.compile(r"(?<!\w)#\w+")
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF️‍←-⇿⌀-⏿]+")
EMOTICON = re.compile(r"(?<!\w)(?:[:;=8xX][-'^]?[)(\]\[DPpOo/\\|*3]+|<3|\^_?\^|[xX]D+)(?!\w)")
HTML_TAG = re.compile(r"<[^>]+>")
HTML_BLOCK = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
HTML_BREAK = re.compile(r"<\s*(br|/p|/div|/li|/h\d|/tr|p|div|li|h\d)\b[^>]*>", re.I)
MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
MD_MARK = re.compile(r"(\*\*|__|\*|_|`+|~~)(?=\S)(.+?)(?<=\S)\1")
MD_MARK_SAFE = re.compile(r"(\*\*|\*|~~)(?=\S)(.+?)(?<=\S)\1")   # no underscores: safe in plain text
LIST_MARK = re.compile(r"^\s*(?:[-*•·>]+|\d+[.)])\s+", re.M)
REPEAT_PUNCT = re.compile(r"([!?¡¿.,])\1+")
ELLIPSIS = re.compile(r"\.{3,}|…")
ELONGATED = re.compile(r"(\w)\1{2,}")
WORD = re.compile(r"\w+(?:['’]\w+)*", re.U)


class Cleaner:
    def __init__(self, cfg: dict | None = None,
                 known_form: Callable[[str], bool] | None = None):
        cfg = cfg or {}
        self.abbrev = {k.lower(): v for k, v in (cfg.get("abbreviations") or {}).items()}
        self.ignore = [re.compile(p, re.I) for p in cfg.get("ignore_patterns", [])]
        self.caps_ratio = cfg.get("all_caps_ratio", 0.7)
        self.split_lines = cfg.get("split_on_newlines", True)
        self.known_form = known_form or (lambda w: False)

    # ---- entry point ----------------------------------------------------
    def segments(self, text: str, fmt: str = "auto") -> list[Segment]:
        text = unicodedata.normalize("NFC", text)
        if fmt == "auto":
            fmt = "html" if re.search(r"<(p|div|br|span|a|li|html|body)\b", text, re.I) else "text"
        if fmt == "html":
            text = self._strip_html(text)
        elif fmt == "markdown":
            text = MD_LINK.sub(r"\1", text)
            text = MD_MARK.sub(r"\2", text)
            text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
        # Markdown links/emphasis are common in plain internet text too
        if fmt != "markdown":
            text = MD_LINK.sub(r"\1", text)
            text = MD_MARK_SAFE.sub(r"\2", text)

        out = []
        if self.split_lines:
            # blank lines always split; single newlines split too, since chat/social
            # text often omits final punctuation
            pieces = [(m.start(), m.group()) for m in re.finditer(r"[^\n]+", text)]
        else:
            pieces = [(m.start(), m.group()) for m in re.finditer(r"(?:[^\n]|\n(?!\s*\n))+", text)]
        for start, piece in pieces:
            if not piece.strip():
                continue
            seg = self.clean(piece)
            seg.start, seg.end = start, start + len(piece)
            if seg.clean:
                out.append(seg)
        return out

    def _strip_html(self, text: str) -> str:
        text = HTML_BLOCK.sub(" ", text)
        text = HTML_BREAK.sub("\n", text)
        text = HTML_TAG.sub(" ", text)
        return html.unescape(text)

    # ---- per-line cleaning -------------------------------------------------
    def clean(self, original: str) -> Segment:
        """Clean one line. Every removed or rewritten item is recorded with `pos`, a
        character offset into the cleaned text, so it can later be attached to the
        sentence it came from:
          - removed items (url, emoji, laughter…): end of the word before them
            (start of line if none), so "¿qué tal? 😂" belongs to "¿qué tal?";
          - rewritten words (abbreviation, elongation): start of the word itself.
        Positions are tracked as word indices through the edits, then converted to
        offsets in the final string."""
        flags: list[str] = []
        s = LIST_MARK.sub("", original)

        # 1. remove non-lexical spans in one pass; earlier patterns win overlaps
        kinds = [("url", URL), ("email", EMAIL), ("mention", MENTION), ("hashtag", HASHTAG),
                 ("emoji", EMOJI), ("emoticon", EMOTICON)] + [("interjection", p) for p in self.ignore]
        spans: list[tuple[int, int, str, str]] = []
        for kind, pat in kinds:
            for m in pat.finditer(s):
                if m.group() and not any(m.start() < e and b < m.end() for b, e, _, _ in spans):
                    spans.append((m.start(), m.end(), kind, m.group()))
        spans.sort()
        removed: list[tuple[dict, int]] = []          # (item, number of words before it)
        out, pos = [], 0
        for b, e, kind, text in spans:
            out.append(s[pos:b])
            removed.append(({"type": kind, "text": text}, len(WORD.findall("".join(out)))))
            out.append(" ")
            pos = e
        out.append(s[pos:])
        s = "".join(out)

        s = ELLIPSIS.sub("...", s)
        s = REPEAT_PUNCT.sub(r"\1", s)

        # 2. word-level normalisation, tracking old word index -> new word index
        rewritten: list[tuple[dict, int]] = []        # (item, index of the new word)
        old_to_new: list[int] = []
        counter = [0]

        def fix_word(m):
            w = m.group()
            new = self._de_elongate(w) if ELONGATED.search(w) else w
            item = None
            ab = self.abbrev.get(new.lower())
            if ab is not None:
                new = ab[0].upper() + ab[1:] if new[:1].isupper() else ab
                item = {"type": "abbreviation", "text": w, "as": new}
            elif new != w:
                item = {"type": "elongation", "text": w, "as": new}
            old_to_new.append(counter[0])
            if item:
                rewritten.append((item, counter[0]))
            counter[0] += max(1, len(WORD.findall(new)))
            return new
        s = WORD.sub(fix_word, s)
        total = counter[0]

        letters = [c for c in s if c.isalpha()]
        if len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) >= self.caps_ratio:
            s = s.lower()
            s = re.sub(r"(^\W*)(\w)", lambda m: m.group(1) + m.group(2).upper(), s, count=1)
            flags.append("all_caps")

        s = re.sub(r"\s+([,.;:!?)\]])", r"\1", s)
        s = re.sub(r"([¿¡(\[])\s+", r"\1", s)
        s = re.sub(r"\s{2,}", " ", s).strip()
        s = re.sub(r"^[,.;:\s]+", "", s)

        # 3. word indices -> character offsets in the final text
        word_spans = [m.span() for m in WORD.finditer(s)]
        ok = len(word_spans) == total
        ignored: list[dict] = []
        for item, before in removed:
            k = old_to_new[before] if before < len(old_to_new) else total   # new words before
            item["pos"] = word_spans[k - 1][1] if ok and k > 0 else 0
            ignored.append(item)
        for item, idx in rewritten:
            item["pos"] = word_spans[idx][0] if ok and idx < len(word_spans) else 0
            ignored.append(item)
        ignored.sort(key=lambda i: i["pos"])
        return Segment(original=original, clean=s, start=0, end=len(original),
                       ignored=ignored, flags=flags)

    @staticmethod
    def internet_text(items: list[dict]) -> bool:
        return any(i["type"] in ("url", "mention", "hashtag", "emoji") for i in items)

    def _de_elongate(self, w: str) -> str:
        """holaaaa -> hola, carrrro -> carro, leeeer -> leer: try collapsing each long
        run to 2 or 1 characters and keep a variant the vocabulary knows."""
        runs = list(ELONGATED.finditer(w))
        options = [""]
        pos = 0
        for m in runs:
            options = [o + w[pos:m.start()] for o in options]
            ch = m.group(1)
            options = [o + ch * k for o in options for k in (1, 2)]
            pos = m.end()
        options = [o + w[pos:] for o in options][:16]
        for o in options:
            if self.known_form(o.lower()):
                return o
        return options[0]   # all runs collapsed to one char

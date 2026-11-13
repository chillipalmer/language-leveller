# Language Leveller

Language Leveller (LL) takes any text — a novel, a news article, a forum thread, a tweet —
splits it into sentences, and gives each sentence a CEFR level for its **vocabulary** and its
**grammar**. It is the core process of a language-learning app, with no interface of its own:
a Python library plus a small command-line tool.

You supply two files per language:

1. a **frequency vocabulary list** — rank, word, part of speech, gloss, and optionally CEFR
   level, inflected variants and transliteration;
2. a **CEFR-graded grammar profile** — grammar features, each with a level and a pattern.

LL does the rest:

```
text ─► clean ─► parse (Universal Dependencies) ─► correct morphology
     ─► rank every word by lemma ─► match grammar features ─► one record per sentence
```

## Quick start

```bash
pip install -e ".[spacy,dev]"
python -m spacy download es_core_news_md

leveller explain --lang languages/es "Si lo hubiera sabido, no habría venido."
leveller level   --lang languages/es article.html --format jsonl > levels.jsonl
leveller test-grammar --lang languages/es
```

```python
from language_leveller import Leveller

ll = Leveller.from_dir("languages/es")          # or vocab_path=..., grammar_path=...
for rec in ll.level_text(open("post.html").read()):
    print(rec["level"], rec["vocab"]["level"], rec["grammar"]["level"], rec["text"])
```

## What a record looks like

```json
{
  "text": "No me lo digas porque ya lo sé",
  "level": "B1",
  "vocab":   {"level": "A1", "max_rank": 52, "coverage": 1.0, "unranked": []},
  "grammar": {"level": "B1", "features": [
      {"id": "es.subj.present", "level": "B1", "label": "Present subjunctive", "tokens": [[3]]},
      {"id": "es.imperative.negative", "level": "B1", "label": "Negative imperative (no + subjunctive)", "tokens": [[0, 3]]}]},
  "tokens": [
      {"i": 3, "text": "digas", "lemma": "decir", "upos": "VERB", "headword": "decir",
       "rank": 28, "level": "A1", "pos": "v", "gloss": "to say, tell", "match": "lemma"}],
  "flags": [],
  "source": {"original": "- No me lo digas xq ya lo sé", "start": 120, "end": 147,
             "ignored": [{"type": "abbreviation", "text": "xq", "as": "porque"}]}
}
```

* `level` is the higher of the vocabulary and grammar levels.
* **Vocabulary level** is the highest band among the sentence's words. Words outside the list
  get rank `N+` (e.g. `5000+`) and the `unranked_level` (default `C2+`). Names, numbers and
  punctuation are excluded.
* **Grammar level** is the highest-level feature found. If none is found, the profile's
  `default_level` applies. Combination rules (e.g. "two different C1 structures → C2") are
  supported.
* `match` says how each word was found: `lemma`, `variant`, `morph`, `form`, `clitic`
  (enclitic pronouns stripped) or `folded` (missing accents).
* `flags`: `low_coverage` (fewer than half the words are known; often a foreign-language
  line), `no_verb`, `short`, `all_caps`, `internet_text`.

## Internet text

Before parsing, LL cleans the input and records everything it changes in `source.ignored`:

- HTML and Markdown are stripped; lists and line breaks become sentence boundaries.
- URLs, emails, @mentions, #hashtags, emoji and emoticons are removed.
- Laughter is removed, using patterns from the language config (`jajaja`, `lol`…).
- Elongated words are repaired using the vocabulary, so `holaaaa` → `hola` but
  `leeeer` → `leer`.
- Chat abbreviations are expanded (`q` → `que`, `xq` → `porque`).
- Each removed or rewritten item is attached to the sentence it came from, even when one
  line holds several sentences.
- Repeated punctuation is collapsed, and ALL-CAPS lines are lowercased.

## Morphology correction

Statistical parsers are unreliable on less frequent verb forms. spaCy's Spanish model, for
example, tags *toques* in "No toques eso" as a noun and *llegues* as indicative. An optional
**morphology lexicon** (`morph.tsv.gz`) lists every known analysis of each form. After
parsing, LL checks each verb against the lexicon and fixes its lemma and features, preferring
lemmas that appear in your frequency list. Every change is reported in the token's
`morph_fix` field.

On the original Spanish grammar test suite, this lifted spaCy `es_core_news_md` from 97/102
to 103/103, and `es_core_news_lg` from 94/102 to 101/103.

Build the lexicon with `tools/build_morph.py`, which reads UniMorph data and/or the verbecc
conjugator. See [docs/ADDING_A_LANGUAGE.md](docs/ADDING_A_LANGUAGE.md).

## Repository layout

```
src/language_leveller/   cleaner, parsing backends, vocab, morph, grammar engine, CLI
languages/es/            config.yaml, grammar.yaml, morph.tsv.gz, vocab.sample.tsv
docs/FORMATS.md          vocabulary, grammar-pattern and config reference
docs/ADDING_A_LANGUAGE.md
tools/build_morph.py     builds a morphology lexicon from UniMorph / verbecc
tests/                   engine tests (no model needed) + Spanish integration tests
```

## Vocabulary lists

Only facts go in the repo: rank, word and POS (plus `level`, `variants` and `translit` if you
created them yourself). Glosses and example sentences from published dictionaries are
copyrightable, so strip them first:

```bash
python tools/strip_vocab.py my_full_list.csv languages/es/vocab.tsv
```

The Spanish list (`languages/es/vocab.tsv`) is derived from the ranks and parts of speech in
Davies, *A Frequency Dictionary of Spanish* (Routledge), with no glosses or examples. When
`vocab.tsv` is absent, LL falls back to `vocab.sample.tsv`, which has illustrative ranks for
tests only.

## Parser backends

`spacy:<model>` (default for Spanish), `stanza:<lang>`, or `conllu` (pre-parsed input from
any UD parser, e.g. UDPipe). The config lists backends in order of preference, and
`--parser` overrides it. The Stanza backend is implemented but has not been run in
development. Stanza usually tags morphology more accurately than spaCy, so it is worth
benchmarking with `leveller test-grammar --parser stanza:es`.

## Benchmark

LL was run over the project's 5,000 graded Spanish sentences, which were levelled earlier by
a separate rule-based checker. The grammar levels agree on **98.7%** of sentences (4,934 of
5,000).

Most of the 66 disagreements are structures the old checker missed and LL finds correctly:
imperatives, present perfects, clefts with *lo que*, and *a los que* relatives. The rest are
genuine ambiguities, such as *-amos* forms, which can be present or preterite.

Participle policy: participles that the vocab lists as adjectives (*cansado*, *abierto*) are
vocabulary. Productive participles (*una decisión mal tomada*) are A2 grammar.

Only 6 sentences contain a word that isn't in the 5,000-word list.

## Known limits

- Grammar detection is pattern-based over a statistical parse. Rare structures can be missed,
  and parser errors can still cause false positives.
- Some forms are genuinely ambiguous without context (*abre* = "opens" or "open!"). LL trusts
  the parser in these cases.
- *ser*/*ir* in the preterite (*fue*, *fueron*) gets whichever lemma the parser picks, so
  *fueron al mar* ("went") can be credited to *ser*.

## Licences

The code is MIT (see `LICENSE`). `languages/es/morph.tsv.gz` is derived from
[UniMorph](https://unimorph.github.io/) Spanish data (from Wiktionary), so it is
**CC BY-SA 3.0**, with gaps filled by [verbecc](https://github.com/bretttolbert/verbecc)
output. See `languages/es/NOTICE`.

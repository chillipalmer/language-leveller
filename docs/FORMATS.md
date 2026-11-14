# File formats

A language lives in its own directory (`languages/<code>/`):

| File | Required | Purpose |
|---|---|---|
| `config.yaml` | yes | parser, level bands, POS mapping, cleaning rules, scoring |
| `vocab.tsv` (or `.csv`) | yes | frequency list |
| `grammar.yaml` | yes | levelled grammar features |
| `morph.tsv.gz` | no | morphology lexicon for correcting the parser |

YAML note: LL reads bare `no`, `yes`, `on` and `off` as words, not booleans. Only
`true`/`false` are booleans.

---

## 1. Vocabulary list

A TSV or CSV file with a header row. Column names are case-insensitive, and columns can
appear in any order.

| Column | Required | Example | Notes |
|---|---|---|---|
| `id` | recommended | `venir_VERB` | stable key the app stores progress against; defaults to `word_pos` |
| `rank` | yes | `112` | frequency rank (1 = most frequent) |
| `word` | yes | `venir` | the lemma (headword) |
| `pos` | yes | `VERB` | Universal POS recommended; other codes are mapped with `vocab.pos_map` |
| `gloss` | no | `to come` | your own wording, senses separated by `;` |
| `level` | no | `A1` | fixes this row's level regardless of bands |
| `feats` | no | `Gender=Fem` | things a learner must memorise, UD syntax |
| `variants` | no | `sólo` | exceptions only: spelling variants, forms the morph lexicon lacks |
| `tags` | no | `region=CL,AR; register=colloquial` | `key=v1,v2` groups separated by `;` |
| `translit` | no | `privet` | romanisation for non-Latin scripts |

All columns are passed through to the output (`id`, `lex_feats`, `tags`), so the app can
use them without a second lookup.

The same word may appear twice with different POS (`como` conj / `como` from *comer*);
LL uses the parser's tag to choose between them.

How a word is looked up, best first:

1. the parser's lemma matches a `word`;
2. the surface form is listed in `variants`;
3. the morphology lexicon gives a lemma that matches a `word`;
4. the surface form equals a `word`.

Steps 1 and 3 also try the parser's lemma rewritten by `lemma_map` and `lemma_suffix`
(config.yaml), for parsers whose lemma convention differs from the list's headwords.
Persian parsers give the past stem (رفت), Persian dictionaries the infinitive (رفتن).

If none of those match, LL tries the clitic-stripped form (`clitic_suffixes`), then an
accent-folded match. Among several matches it prefers a POS-compatible entry, then the more
frequent one.

## 2. Grammar profile

```yaml
language: es
default_level: A1          # level when no feature matches
combinations:              # optional promotion rules
  - {id: es.combo.two_c1, level: C1, min_distinct: 2, result: C2,
     label: Two different C1 structures in one sentence}
features:
  - id: es.subj.imperfect          # unique, stable id (shown in output)
    level: B2                      # must be on the level scale
    label: Imperfect subjunctive
    description: optional notes
    match: <pattern>               # or match_any: [<pattern>, ...]
    tests:                         # run by `leveller test-grammar`
      pos: ["Me pidió que lo ayudara."]   # must match
      neg: ["Me pide que lo ayude."]      # must not match
    except:                        # optional patterns; matches overlapping them are dropped
      - sequence: [{form: o}, {form: sea}]
    source: "Plan Curricular, A2"   # optional, informational: where the level comes from
    regions: [ES]                  # optional ISO 3166 codes where this is standard;
                                   # always detected, reported in output for the app to judge
    enabled: true                  # optional; false skips the feature
```

### Patterns

**token**: one token satisfies a constraint.
```yaml
match: {token: {upos: [VERB, AUX], Mood: Sub, Tense: Imp}}
```

**graph**: named tokens linked by dependency relations. `head: <name>` means "this
token's head is that node".
```yaml
match:
  graph:
    v:   {VerbForm: Part}
    aux: {lemma: haber, Mood: Cnd, rel: aux, head: v}
```

**sequence**: consecutive tokens. Supports gaps, optional elements and back-references.
```yaml
match:
  sequence:
    - {Mood: [Sub, Imp], as: V}      # bind this token as V
    - {gap: [1, 2]}                  # skip 1–2 tokens ({gap: 3} means 0–3)
    - {same_form: V}                 # same surface form as V (also: same_lemma)
```

### Constraint keys

| Key | Matches | Example |
|---|---|---|
| `form` | surface form, case-insensitive | `form: [quien, quienes]` |
| `lemma` | lemma, case-insensitive | `lemma: haber` |
| `upos` | Universal POS | `upos: [VERB, AUX]` |
| `rel` | dependency relation; `aux` also matches `aux:pass` | `rel: [root, conj]` |
| `regex` | regex on the lowercased form | `regex: '^haber'` |
| `sent_start` | first non-punctuation token | `sent_start: true` |
| `clause_start` | first token of the sentence or right after punctuation | `clause_start: true` |
| `has_child` / `no_child` | some / no dependent satisfies a constraint | `no_child: {rel: mark}` |
| `head_is` | the token's head satisfies a constraint | `head_is: {lemma: querer}` |
| `optional` | (sequence only) element may be absent | |
| *any other key* | a UD morphological feature | `Mood: Sub`, `Person: 2`, `Polite: Form` |

Values can be a scalar, a list (matches any of them), `{not: x}` / `{not: [x, y]}`, or
`null` (the feature must be absent).

### Writing patterns

Run `leveller parse --lang languages/xx "a sentence"` to see exactly what the parser
produces, then write the pattern against that. Prefer `token` and `graph` patterns, which
match parser features; use `sequence` for fixed phrases. Add at least one `pos` and one `neg`
test to every feature.

### Vocabulary cutoffs per learner

Bands in `config.yaml` are only the default. Override them per call:
`Leveller.from_dir(..., bands={"A1": 600, "A2": 1200, ...})`, `vocab.set_bands(...)`,
or `--bands A1=600,A2=1200,...` on the command line. Grammar levels always come from
the grammar file.

## 3. config.yaml

```yaml
language: es
name: Spanish
script: LATIN                             # optional; words in other scripts are marked foreign
levels: [A1, A2, B1, B2, C1, C2, C2+]     # optional; the CEFR scale is the default
parser: [spacy:es_core_news_md, stanza:es]
parser_options:                           # optional: Stanza model per processor
  stanza: {packages: {tokenize: perdt_charlm, mwt: perdt, pos: perdt_charlm,
                      lemma: perdt_charlm, depparse: perdt_charlm}}
vocab:
  file: vocab.tsv
  fallback_file: vocab.sample.tsv
  bands: [{level: A1, max_rank: 1000}, ...]
  unranked_level: C2+
  pos_map: {v: [VERB, AUX], n: [NOUN, PROPN], ...}
  exclude_upos: [PUNCT, SYM, PROPN, SPACE]
  exclude_patterns: ['^[IVXLCDM]+$']         # case-sensitive regexes on the form
  clitic_suffixes: ['^(.{2,}?)(me|te|se|lo|la|le|nos|os|los|las|les)$']
  accent_fold_fallback: true
  variant_separator: "|"
  lemma_suffix: {VERB: ن}                    # parser lemma + suffix = headword (Persian رفت -> رفتن)
  lemma_map: {است: بودن}                     # parser lemma -> headword
grammar: {file: grammar.yaml}
morph:
  file: morph.tsv.gz
  verb_cues: [no, me, te, que, ...]          # retag noun → verb after these
  adj_verb_cues: [no, me, te, que, ...]      # stricter list for words the vocab lists as adjectives
  mood_preference: [Ind, Sub, Imp, Cnd]      # tie-break between readings
  initial_subjectless_boost: {mood: Imp, weight: 2}
  capitalised_midsentence_is_name: true     # capitalised words after the first are never verbs
cleaning:
  char_map: {ي: ی, ك: ک}                     # applied first, before parsing and grammar tests
  normalise:                                 # regex rewrites, in order
    - {pattern: '(?<![^\s])(ن?می) +(?=\S)', replace: "\\1\u200c"}
  abbreviations: {q: que, xq: porque}
  ignore_patterns: ['\b(?:ja){2,}\b']
  split_on_newlines: true
  all_caps_ratio: 0.7
scoring:
  unranked_counts: true          # unknown words raise the vocab level
  low_coverage_threshold: 0.5
  coverage_target: 0.98          # used by `leveller profile` (whole-text coverage)
```

## 4. Morphology lexicon

A TSV file, optionally gzipped, with the header `form  lemma  upos  feats`. `feats` uses UD
syntax (`Mood=Sub|Number=Sing|Person=2|Tense=Pres|VerbForm=Fin`). Only verb readings are
used for correction. Noun and adjective rows exist so that ambiguous forms (*toques*) are
recognised as ambiguous.

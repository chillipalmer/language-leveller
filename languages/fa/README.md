# Persian (fa)

## Setup

```bash
pip install stanza
python -c "import stanza; stanza.download('fa')"
leveller test-grammar --lang languages/fa
```

The parser is Stanza, trained on UD Persian-PerDT; spaCy has no Persian model.
`config.yaml` (`parser_options`) selects the character-LM tokenizer and lemmatizer
(`perdt_charlm`) rather than Stanza's default `perdt_nocharlm` ones, which are included
in the default download. On the PerDT dev set, the default tokenizer makes about three
times as many word-splitting errors (word F1 0.9924 vs 0.9973). For example, it splits
*خریدم* into *خرید* + *م*, leaves *کمکم* unsplit, and does not separate *دیدمش* from a
following full stop. The grammar profile was written and tested against the charlm
packages. NER and the other models in the download are not used.

## How the profile works

- **Spelling.** Text is normalised before parsing (`cleaning` in `config.yaml`):
  - Arabic ي/ك become Persian ی/ک, and tatweel is removed.
  - Spaced prefixes and suffixes are joined with a zero-width non-joiner (ZWNJ): *می روم*, *کتاب ها*, *بزرگ تر*, *دیده ام*.
  - The parser misreads the spaced spellings, e.g. *می* as a noun.
- **Lemmas.**
  - Stanza gives verbs their past stem (*رفت*). `vocab.lemma_suffix` adds ن to reach the list's infinitive (*رفتن*).
  - `vocab.lemma_map` handles the copula (*است*, *هست* → *بودن*) and *توان*.
  - It also maps lemmas PerDT keeps for inflected forms: *آنها* (also the lemma of the clitic *شان*) → *آن*, *یکی* → *یک*, *اولین* → *اول*, and the present stem *گذارد* (*بگذارد*, *می‌گذارم*, *گذارده*) → *گذاشتن*.
  - `lemma_rules` restores *شد* where PerDT lemmatises passive *شد / می‌شود* as *کرد*.
- **Grammar patterns.**
  - PerDT marks mood only on imperatives and some auxiliaries. The present subjunctive and the past imperfective both come out with no Tense, and participles often lack `VerbForm=Part`.
  - So patterns combine UPOS, lemma and relation with regexes on prefixes (می‌, ب, ن, and the preverbs بر/در/باز/فرو/فرا/وا/ور) and endings (the participle's ه, person endings).
- **Levels** follow the Saadi Foundation's grammar course *Chaarchoob* (چارچوب), written for its Persian Teaching Standard Reference (PTSR). Each feature's `source` names the lesson where the structure is first taught.
  - Volume 1 covers PTSR elementary and pre-intermediate; volume 2 covers intermediate and upper-intermediate. The PTSR equates pre-intermediate with CEFR A2, intermediate with B1 and upper-intermediate with B2.
  - The books do not level single lessons, so lessons are mapped by position: volume 1 lessons 1–25 → A1, 26–35 → A2; volume 2 lessons 1–13 → B1, 14–27 → B2.
  - C1–C2 features are not in volumes 1–2. Volume 3 (advanced) has no published contents page, so those levels are unchecked.
  - Two project decisions override the position rule, and their `source` says so:
    - relative clauses with *که* (volume 2, lesson 20, which the rule makes B2) are B1, in line with CEFR-aligned courses for other languages;
    - *را* (taught explicitly only in volume 2, lesson 3) is A2, because it occurs throughout volume 1.
- **Regional:** `fa.dari.copula` (*استم*, *استی*, …) is tagged `regions: [AF]`.

## Checking against the treebank

```bash
git clone --depth 1 https://github.com/UniversalDependencies/UD_Persian-PerDT
python tools/fa_eval_perdt.py UD_Persian-PerDT/fa_perdt-ud-dev.conllu
```

Results on the dev set (1,456 sentences, Stanza `perdt_charlm` models, 14 Nov 2026):

| Feature | Precision | Recall |
|---|---|---|
| Past imperfective | 0.97 | 0.99 |
| Present subjunctive | 0.88 | 0.86 |
| Simple past | 1.00 | ≈1.00 (see note) |

- **Simple past:** the script's own recall figure (~0.73) is understated. Gold "simple past" also counts future main verbs and short infinitives, which LL correctly does not count as simple past.
- **Present subjunctive:** most errors are 2nd-person plural forms that could be imperative or subjunctive (*بگویید*).

## Known limits

- **Compound verbs:** compound (light-verb) verbs such as *نشان دادن* and *کار کردن* are listed in `vocab.tsv` but cannot match. LL looks words up one at a time; multiword expressions are still undecided.
- **Passive with شدن:** LL cannot tell a passive compound verb with *شدن* (*انجام شد*) from *شدن* meaning "become" (*سرد شد*), so only the participle passive (*ساخته شد*) is detected. Compound verbs with *گردیدن* are detected as the formal passive.
- **Split words:** the parser sometimes splits *دارم* into *دار* + *م*. The present progressive pattern allows for this.
- **Colloquial Tehrani spellings** (*میرم*, *اومدم*, *میخوام*) are not normalised.

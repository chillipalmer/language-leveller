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
  - More of the same: *آنان*, *اینها* → *آن*, *این*; *دیگری* (also the lemma of *دیگران*), *بسیاری*, *تمامی*, *توی*, *نخستین*, *آخرین*, *بیشتر*, *هزاران*; the ezafe forms *جلوی*, *جای*, *پای*; and the stems *خاست*, *رسانید*, *گردانید*.
  - PerDT drops verb prefixes from lemmas (*برداشت* → *داشت*, *درآورد* → *آورد*, *برگشت* → *گشت*). `vocab.lemma_prefixes` restores them: a verb whose surface form starts with بر, در, باز, فرا or وا is tried as prefix + lemma first, and used if that infinitive is listed.
  - Arabic plurals are counted under the singular, as in the source list: PerDT already does this (*افراد* → *فرد*) except for *شرایط*, *اطلاعات* and *همگان*, which `lemma_map` handles.
  - Spelling variants (*مسأله*, *هیأت*, *رییس*, *گفتگو*, *معنی*) are in the `variants` column; LL also checks the parser's lemma against variants, so plurals such as *مسأله‌ها* match.
  - `lemma_rules` restores *شد* where PerDT lemmatises passive *شد / می‌شود* as *کرد*.
- **Grammar patterns.**
  - PerDT marks mood only on imperatives and some auxiliaries. The present subjunctive and the past imperfective both come out with no Tense, and participles often lack `VerbForm=Part`.
  - So patterns combine UPOS, lemma and relation with regexes on prefixes (می‌, ب, ن, and the preverbs بر/در/باز/فرو/فرا/وا/ور) and endings (the participle's ه, person endings).
- **Levels** follow the usual order of Persian-as-a-foreign-language courses. They are provisional, because no official Persian CEFR grammar inventory is available in machine-readable form.
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
- **Prefix check:** `lemma_prefixes` only looks at the start of the surface form. Subjunctive ب + a verb beginning with ر (*برساند*) also starts with بر; this is harmless while no listed بر- verb matches ب + ر- + stem, but check new بر- verbs added to the list.
- **Colloquial Tehrani spellings** (*میرم*, *اومدم*, *میخوام*) are not normalised.

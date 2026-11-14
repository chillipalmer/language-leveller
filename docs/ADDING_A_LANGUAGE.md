# Adding a language

1. **Choose a parser.** spaCy has UD-style models for about 25 languages, Stanza for about
   70, and UDPipe for more (feed its CoNLL-U output through the `conllu` backend). Check
   that the model outputs UD morphological features. `leveller parse` shows them.

2. **Create `languages/<code>/config.yaml`.** Copy the Spanish one, then set the parser,
   the rank bands, a `pos_map` for your list's POS codes, and cleaning rules
   (abbreviations, laughter). Remove `clitic_suffixes` if the language has no enclitics.
   If the language uses a different scale (e.g. pre-A1), set `levels:`.

3. **Add your vocabulary list** as `vocab.tsv` (see `docs/FORMATS.md`). For non-Latin
   scripts, fill `translit`.

4. **Write `grammar.yaml`.** Start from an official inventory where one exists: the
   Instituto Cervantes Plan Curricular (Spanish), the English Grammar Profile, Profile
   Deutsch, and so on. For each feature, parse a few example sentences with
   `leveller parse`, then write the pattern against what the parser actually produces.
   - Inflecting languages (Russian, Arabic) mostly need `token` patterns on features.
   - Languages with little inflection (Mandarin, Vietnamese) mostly need `sequence` and
     `graph` patterns on lemmas, e.g. 把 constructions, aspect particles 了/过/着.
   - Persian: the PerDT-trained parser leaves mood and often tense unmarked, so
     `languages/fa/grammar.yaml` matches prefixes and endings with `regex` alongside
     UPOS, lemma and relation. Normalise spelling first (`cleaning.char_map`,
     `cleaning.normalise`): the parser only reads the ZWNJ spelling می‌روم correctly.
   - Japanese and Korean: UD tokenisation splits verb endings into separate AUX tokens, so
     write `graph` patterns over them.

5. **(Optional) Build a morphology lexicon.** UniMorph covers about 170 languages:
   ```bash
   git clone https://github.com/unimorph/<iso3>
   python tools/build_morph.py --unimorph <iso3>/<iso3> --out languages/<code>/morph.tsv.gz
   ```
   UniMorph has gaps. Spanish lacks *tener*, *poner* and *venir*. For Spanish, the build
   therefore also conjugates every verb in your list with verbecc
   (`--verbecc es --vocab languages/es/vocab.tsv`). verbecc also supports French, Italian,
   Portuguese, Romanian and Catalan, but `tools/build_morph.py` has a tense mapping for
   Spanish only so far.

   Rebuild the Spanish lexicon against your full list:
   ```bash
   pip install verbecc
   python tools/build_morph.py --unimorph spa/spa --verbecc es \
       --vocab languages/es/vocab.tsv --extra-verbs "$(cat tools/es_extra_verbs.txt)" \
       --out languages/es/morph.tsv.gz
   ```

6. **Test.** `leveller test-grammar --lang languages/<code>` must pass. Then run
   `leveller explain` on a page of real text and read the output.

"""Candidate lemmas beyond the current list, with lemma-level frequencies.

Usage: python candidates.py VOCAB MILLER STEMS SUBTITLES COLLOQ PERDT_DIR OUTDIR

Forms in the subtitle list and wordfreq that mapforms.py credits to no entry
are lemmatized with a form -> lemma table built from UD Persian-PerDT (most
frequent analysis wins). Forms PerDT doesn't know are kept as their own lemma.
Writes OUTDIR/candidates.tsv: lemma, pos, subtitle count, wordfreq frequency,
PerDT count, example forms.
"""
import sys, os, glob, collections, runpy

VOCAB, MILLER, STEMS, SUBS, COLLOQ, PERDT, OUT = sys.argv[1:8]
here = os.path.dirname(os.path.abspath(__file__))
# reuse mapforms.py: run it in-process up to the credit step
sys.argv = ['mapforms.py', VOCAB, MILLER, STEMS, SUBS, COLLOQ, OUT]
src = open(os.path.join(here, 'mapforms.py'), encoding='utf-8').read()
src = src.split("for form, target in colloq.items():\n    if target == 'IGNORE-SUBS'")[0]
g = {'__name__': 'mapforms_lib'}
exec(compile(src, 'mapforms.py', 'exec'), g)
norm, cands, colloq, subs, wf = g['norm'], g['cands'], g['colloq'], g['subs'], g['wf']

# PerDT form -> (lemma, upos)
table = collections.defaultdict(collections.Counter)
lemma_count = collections.Counter()
for path in glob.glob(os.path.join(PERDT, '*.conllu')):
    for line in open(path, encoding='utf-8'):
        if not line.strip() or line.startswith('#'):
            continue
        c = line.rstrip('\n').split('\t')
        if len(c) != 10 or '-' in c[0] or '.' in c[0]:
            continue
        form, lemma, upos = norm(c[1]), norm(c[2]), c[3]
        if upos in ('PUNCT', 'NUM', 'X', 'SYM'):
            continue
        if upos == 'VERB' and not lemma.endswith('ن'):
            lemma = lemma.split('#')[0] + 'ن'   # past stem -> infinitive
        table[form][(lemma, upos)] += 1
        lemma_count[(lemma, upos)] += 1

# bare colloquial verb forms (کنه، باشه، شه) and detached suffixes: pieces of
# known words that tokenization split off, not new lemmas
bare_coll = {'ها', 'های', 'هایی', 'هام', 'هات', 'هاش', 'ترین', 'تر', 'تری', 'مون', 'تون', 'شون',
             'می', 'نمی', 'ای', 'ی', 'ام', 'ات', 'اش', 'اند', 'ایم', 'اید', 'یی'}
for e in g['entries']:
    if e['pos'] == 'VERB' and ' ' not in e['word']:
        for S in g['present_stems'](norm(e['word'])):
            for b in [S] + sorted(g['colloquial_bases'](S)):
                for end in ['م', 'ی', 'ه', 'د', 'یم', 'ین', 'ن', 'ید', 'ند']:
                    bare_coll.add(b + end)
known_words = set()
for e in g['entries']:
    known_words.add(norm(e['word']))
for t in colloq.values():
    if t.startswith('NEW:'):
        known_words.add(norm(t.split(':')[1]))

agg = collections.defaultdict(lambda: {'subs': 0.0, 'wf': 0.0, 'forms': collections.Counter()})
def add(counter, key):
    for form, c in counter.items():
        if len(form) <= 1 or form in cands or form in colloq:
            continue
        if any(ch.isascii() for ch in form):
            continue
        if form in table:
            lemma, upos = table[form].most_common(1)[0][0]
        else:
            lemma, upos = form, '?'
        if lemma in known_words or lemma in cands or lemma in colloq:
            continue
        if form in bare_coll or lemma in bare_coll:
            continue
        a = agg[(lemma, upos)]
        a[key] += c
        a['forms'][form] += c if key == 'subs' else c * 1e6
add(subs, 'subs')
add(wf, 'wf')

with open(os.path.join(OUT, 'candidates.tsv'), 'w', encoding='utf-8') as f:
    f.write('lemma\tpos\tsubs\twordfreq\tperdt\tforms\n')
    for (lemma, upos), a in sorted(agg.items(), key=lambda kv: -(kv[1]['wf'] * 1e6 + kv[1]['subs'] / 41))[:40000]:
        forms = ' '.join(f for f, _ in a['forms'].most_common(4))
        f.write(f"{lemma}\t{upos}\t{a['subs']:.0f}\t{a['wf']:.3e}\t{lemma_count[(lemma, upos)]}\t{forms}\n")
print('candidate lemmas', len(agg))

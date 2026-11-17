"""Counts for the words added to take the list to 10,000.

Usage: python extend.py CANDIDATES ADDED SUBTITLES OUT

CANDIDATES is candidates.tsv from candidates.py; ADDED is added.tsv, the
hand-reviewed words with the candidate lemmas (`keys`) whose forms belong to
them. A candidate lemma with several POS rows goes to the added word of the
same POS where there is one. A word no candidate row reaches is counted from
its own form. Writes OUT: word, pos, subs, wordfreq.
"""
import csv, collections, re, sys
from wordfreq import top_n_list, word_frequency

CANDS, ADDED, SUBS, OUT = sys.argv[1:5]

def norm(s):
    s = s.replace('ي', 'ی').replace('ك', 'ک').replace('ة', 'ه').replace('ى', 'ی').replace('أ', 'ا').replace('إ', 'ا').replace('ؤ', 'و')
    s = re.sub('[‌‍ـً-ْٰ]', '', s)
    return s.strip()

added = list(csv.DictReader(open(ADDED, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE))
bykey = collections.defaultdict(list)
for a in added:
    a['subs'], a['wf'] = 0.0, 0.0
    for k in a['keys'].split('|'):
        bykey[k].append(a)
reached = set()
for c in csv.DictReader(open(CANDS, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE):
    owners = bykey.get(c['lemma'])
    if not owners:
        continue
    same = [a for a in owners if a['pos'] == c['pos']]
    a = (same or owners)[0]
    a['subs'] += float(c['subs'])
    a['wf'] += float(c['wordfreq'])
    reached.add(id(a))

subs = collections.Counter()
for line in open(SUBS, encoding='utf-8'):
    w, n = line.rsplit(' ', 1)
    subs[norm(w)] += int(n)
wf = collections.Counter()
for w in top_n_list('fa', 100000):
    wf[norm(w)] += word_frequency(w, 'fa')
own = 0
for a in added:
    if id(a) not in reached:
        a['subs'], a['wf'] = subs.get(norm(a['word']), 0), wf.get(norm(a['word']), 0)
        own += 1
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('word\tpos\tsubs\twordfreq\n')
    for a in added:
        f.write(f"{a['word']}\t{a['pos']}\t{a['subs']:.0f}\t{a['wf']:.3e}\n")
print(len(added), 'added words;', own, 'counted from their own form;',
      sum(1 for a in added if a['subs'] == 0 and a['wf'] == 0), 'with no count')

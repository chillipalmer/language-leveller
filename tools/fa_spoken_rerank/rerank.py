"""Reweight vocab ranks with spoken evidence.

Usage: python rerank.py OUTDIR [ADDED_COUNTS SIZE]
  (reads and writes the files mapforms.py made there)


score = exp((W_M*log r_miller + W_S*log r_spoken) / (W_M + W_S))
r_spoken = geometric mean of an entry's rank by subtitle count and by wordfreq
frequency, both ranked among all single-word, non-name entries plus new words.
Multiword entries, names and placeholder ranks keep r_spoken = r_miller.
Words outside Miller's list have no r_miller; their rank by wordfreq frequency
in the same pool stands in for it (r_written).
With ADDED_COUNTS (from extend.py) and SIZE, the best-scoring added words are
kept until the list holds SIZE rows.
"""
import csv, math, sys, collections, os
OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
ADDED = sys.argv[2] if len(sys.argv) > 2 else None
SIZE = int(sys.argv[3]) if len(sys.argv) > 3 else None
W_M, W_S = 2.0, 1.0

rows = list(csv.DictReader(open(os.path.join(OUT, 'entry_counts.tsv'), encoding='utf-8'), delimiter='\t'))
new = []
for line in open(os.path.join(OUT, 'new_counts.tsv'), encoding='utf-8'):
    t, s, w = line.rstrip('\n').split('\t')
    _, lemma, pos = t.split(':')
    new.append({'id': f'{lemma}_{pos}', 'rank': '0', 'word': lemma, 'pos': pos,
                'subs': s, 'wordfreq': w, 'multiword': '0', 'new': '1'})
added = []
if ADDED:
    have = {r['id'] for r in rows + new}
    for r in csv.DictReader(open(ADDED, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE):
        rid = f"{r['word']}_{r['pos']}"
        if rid not in have:
            added.append({'id': rid, 'rank': '0', 'word': r['word'], 'pos': r['pos'], 'subs': r['subs'],
                          'wordfreq': r['wordfreq'], 'multiword': '0', 'new': '2'})
def measurable(r):
    return r['multiword'] == '0' and r['pos'] != 'PROPN' and int(r['rank']) <= 5000 or r.get('new') in ('1', '2')
def rank_by(key, meas):
    N = len(meas) + 1
    vals = sorted(((float(r[key]), r['id'], i) for i, r in enumerate(meas)), key=lambda v: (-v[0], v[1]))
    out = {}
    for pos, (v, _, i) in enumerate(vals, 1):
        out[meas[i]['id']] = pos if v > 0 else N
    return out
def score(allr):
    meas = [r for r in allr if measurable(r)]
    rs, rw = rank_by('subs', meas), rank_by('wordfreq', meas)
    for r in allr:
        rm = int(r['rank']) if r.get('new') not in ('1', '2') else rw[r['id']]
        if measurable(r):
            rsp = math.sqrt(rs[r['id']] * rw[r['id']])
        else:
            rsp = rm
        r['r_m'], r['r_sp'] = rm, rsp
        r['score'] = math.exp((W_M * math.log(rm) + W_S * math.log(rsp)) / (W_M + W_S))
allr = rows + new + added
score(allr)
if SIZE:
    room = SIZE - len(rows) - len(new)
    keep = {r['id'] for r in sorted(added, key=lambda r: (r['score'], r['id']))[:room]}
    allr = rows + new + [r for r in added if r['id'] in keep]
    score(allr)
# placeholder ranks (rare readings of homographs, 5001+) stay at the end, in order
isnew = lambda r: r.get('new') in ('1', '2')
main = [r for r in allr if isnew(r) or int(r['rank']) <= 5000]
tail = sorted([r for r in allr if not isnew(r) and int(r['rank']) > 5000], key=lambda r: int(r['rank']))
# homographs split from one source entry share its rank: group by (old rank, word)
groups = collections.defaultdict(list)
for r in main:
    key = (r['rank'], r['word']) if not isnew(r) else (r['id'],)
    groups[key].append(r)
gorder = sorted(groups.values(), key=lambda g: (min(x['score'] for x in g), min(int(x['rank']) for x in g), min(x['id'] for x in g)))
newrank = {}
for n, g in enumerate(gorder, 1):
    for r in g:
        newrank[r['id']] = n
last = len(gorder)
for n, r in enumerate(tail, last + 1):
    newrank[r['id']] = n
order = sorted(allr, key=lambda r: (newrank[r['id']], r['id']))
with open(os.path.join(OUT, 'reranked.tsv'), 'w', encoding='utf-8') as f:
    f.write('id\tword\tpos\told\tnew\tr_written\tr_spoken\tsubs\tisnew\n')
    for r in order:
        f.write(f"{r['id']}\t{r['word']}\t{r['pos']}\t{r['rank']}\t{newrank[r['id']]}\t{r['r_m']}\t{r['r_sp']:.0f}\t{r['subs']}\t{r.get('new','0')}\n")
print(len(allr), 'rows;', sum(1 for r in allr if r.get('new') == '2'), 'added words kept')

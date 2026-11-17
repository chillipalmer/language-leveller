"""Reweight vocab ranks with spoken evidence.

Usage: python rerank.py OUTDIR   (reads and writes the files mapforms.py made there)


score = exp((W_M*log r_miller + W_S*log r_spoken) / (W_M + W_S))
r_spoken = geometric mean of an entry's rank by subtitle count and by wordfreq
frequency, both ranked among all single-word, non-name entries plus new words.
Multiword entries, names and placeholder ranks keep r_spoken = r_miller.
"""
import csv, math, sys, collections, os
OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
W_M, W_S = 2.0, 1.0
NEW_MILLER = 5500

rows = list(csv.DictReader(open(os.path.join(OUT, 'entry_counts.tsv'), encoding='utf-8'), delimiter='\t'))
new = []
for line in open(os.path.join(OUT, 'new_counts.tsv'), encoding='utf-8'):
    t, s, w = line.rstrip('\n').split('\t')
    _, lemma, pos = t.split(':')
    new.append({'id': f'{lemma}_{pos}', 'rank': str(NEW_MILLER), 'word': lemma, 'pos': pos,
                'subs': s, 'wordfreq': w, 'multiword': '0', 'new': '1'})
allr = rows + new
def measurable(r):
    return r['multiword'] == '0' and r['pos'] != 'PROPN' and int(r['rank']) <= 5000 or r.get('new') == '1'
meas = [r for r in allr if measurable(r)]
N = len(meas) + 1
def rank_by(key):
    vals = sorted(((float(r[key]), r['id'], i) for i, r in enumerate(meas)), key=lambda v: (-v[0], v[1]))
    out = {}
    for pos, (v, _, i) in enumerate(vals, 1):
        out[meas[i]['id']] = pos if v > 0 else N
    return out
rs, rw = rank_by('subs'), rank_by('wordfreq')
for r in allr:
    rm = int(r['rank'])
    if measurable(r):
        rsp = math.sqrt(rs[r['id']] * rw[r['id']])
    else:
        rsp = rm
    r['r_sp'] = rsp
    r['score'] = math.exp((W_M * math.log(rm) + W_S * math.log(rsp)) / (W_M + W_S))
# placeholder ranks (rare readings of homographs, 5001+) stay at the end, in order
main = [r for r in allr if r.get('new') == '1' or int(r['rank']) <= 5000]
tail = sorted([r for r in allr if r.get('new') != '1' and int(r['rank']) > 5000], key=lambda r: int(r['rank']))
# homographs split from one source entry share its rank: group by (old rank, word)
groups = collections.defaultdict(list)
for r in main:
    key = (r['rank'], r['word']) if r.get('new') != '1' else (r['id'],)
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
    f.write('id\tword\tpos\told\tnew\tr_spoken\tsubs\tisnew\n')
    for r in order:
        f.write(f"{r['id']}\t{r['word']}\t{r['pos']}\t{r['rank']}\t{newrank[r['id']]}\t{r['r_sp']:.0f}\t{r['subs']}\t{r.get('new','0')}\n")

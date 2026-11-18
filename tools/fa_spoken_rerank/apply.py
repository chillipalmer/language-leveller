"""Write reweighted ranks and the added words into vocab.tsv.

Usage: python apply.py VOCAB RERANKED NEW_ROWS [ADDED]

Existing rows keep every column but rank. Added words take their metadata from
NEW_ROWS (and ADDED, the 10k extension) and are tagged rank=estimated; added
words that RERANKED doesn't rank (cut by the size limit) are left out, and so
are earlier added rows it no longer ranks. The file is rewritten in rank order.
"""
import csv, sys

VOCAB, RERANKED = sys.argv[1:3]
NEW_FILES = sys.argv[3:]
cols = ['id', 'rank', 'word', 'pos', 'gloss', 'feats', 'variants', 'tags', 'translit']

rows = list(csv.DictReader(open(VOCAB, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE))
newrank = {r['id']: int(r['new']) for r in csv.DictReader(open(RERANKED, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE)}
rows = [r for r in rows if r['id'] in newrank or 'rank=estimated' not in r['tags']]
have = {r['id'] for r in rows}
for path in NEW_FILES:
    for r in csv.DictReader(open(path, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE):
        rid = f"{r['word']}_{r['pos']}"
        if rid in have or rid not in newrank:
            continue
        have.add(rid)
        tags = '; '.join(t for t in ['rank=estimated', r['tags']] if t)
        rows.append({'id': rid, 'rank': '', 'word': r['word'], 'pos': r['pos'], 'gloss': r['gloss'],
                     'feats': '', 'variants': r['variants'], 'tags': tags, 'translit': r['translit']})
missing = [r['id'] for r in rows if r['id'] not in newrank]
if missing:
    sys.exit(f'no new rank for {missing[:10]}')
for i, r in enumerate(rows):
    r['rank'] = str(newrank[r['id']])
    r['_order'] = i
rows.sort(key=lambda r: (int(r['rank']), r['_order']))
with open(VOCAB, 'w', encoding='utf-8', newline='') as f:
    f.write('\t'.join(cols) + '\n')
    for r in rows:
        f.write('\t'.join(r[c] for c in cols) + '\n')
print(len(rows), 'rows written')

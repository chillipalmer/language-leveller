"""Write reweighted ranks and the added words into vocab.tsv.

Usage: python apply.py VOCAB RERANKED NEW_ROWS

Existing rows keep every column but rank. Added words take their metadata from
NEW_ROWS and are tagged rank=estimated. The file is rewritten in rank order.
"""
import csv, sys

VOCAB, RERANKED, NEW_ROWS = sys.argv[1:4]
cols = ['id', 'rank', 'word', 'pos', 'gloss', 'feats', 'variants', 'tags', 'translit']

rows = list(csv.DictReader(open(VOCAB, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE))
newrank = {r['id']: int(r['new']) for r in csv.DictReader(open(RERANKED, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE)}
have = {r['id'] for r in rows}
for r in csv.DictReader(open(NEW_ROWS, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE):
    rid = f"{r['word']}_{r['pos']}"
    if rid in have:
        continue
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

"""Usage: python tools/cognate_candidates_translit.py languages/fa/vocab.tsv out.json

Persian: compare the vocab row's transliteration with its English gloss senses.
Loanwords from French/English (telefon, polis, film) score high; inherited Indo-European
cognates (mɑdær ~ mother, bærɑdær ~ brother) score lower and are sent to review.
Bands: yes = score >= 0.85 on the first sense; review = max(score, mean(score, skeleton)) >= 0.70."""
import csv, re, sys, json, difflib, os

def fa_latin(t):
    t = t.split('/')[0].strip().lower()
    for a, b in [('ɑ','a'),('æ','a'),('ʃ','sh'),('ʒ','zh'),('x','kh'),('ɣ','gh'),('ʔ',''),('ː',''),('j','y'),
                 ('ˈ',''),('-',''),(' ','')]:
        t = t.replace(a, b)
    return t

def en_phon(w):
    w = w.lower()
    for a, b in [('tion','sion'),('ph','f'),('ck','k'),('qu','k'),('w','v'),('x','ks'),('oo','u'),('ou','u'),
                 ('th','t')]:
        w = w.replace(a, b)
    w = re.sub(r'c(?=[eiy])', 's', w); w = w.replace('c', 'k'); w = w.replace('y', 'i')
    w = re.sub(r'(.)\1', r'\1', w)           # double letters
    w = re.sub(r'e$', '', w)                 # silent final e
    return w

def skel(w):            # consonant skeleton, voicing merged
    w = re.sub(r'[aeiouy]', '', w)
    for a, b in [('d','t'),('b','p'),('g','k'),('z','s'),('v','f'),('kh','k'),('sh','s'),('zh','s'),('gh','k')]:
        w = w.replace(a, b)
    return w

def sim(a, b):
    r = difflib.SequenceMatcher(None, a, b).ratio()
    p = len(os.path.commonprefix([a, b]))
    return max(r, min(1.0, 0.5 * r + 0.5 * p / max(len(a), len(b))))

def senses(gloss, pos):
    out = []
    for s in gloss.split(';'):
        s = re.sub(r'\(.*?\)|\[.*?\]', '', s).strip()
        if s[:1].isupper():          # a proper-name sense (Iran, Mehr, Putin): not a cognate
            continue
        s = s.lower()
        if pos == 'VERB': s = re.sub(r'^to\s+', '', s)
        s = re.sub(r'^(a|an|the)\s+', '', s)
        if s: out.append(s)
    return out

rows = list(csv.DictReader(open(sys.argv[1]), delimiter='\t'))
res = []
for r in rows:
    if not r['translit'] or r['pos'] == 'PROPN': continue
    lat = fa_latin(r['translit'])
    best = (0, '', None, 0)
    for i, s in enumerate(senses(r['gloss'], r['pos'])):
        for w in {s, *s.split()}:
            if len(w) < 3 or len(lat) < 3: continue
            e = en_phon(w)
            sc = sim(lat, e)
            sk = sim(skel(lat), skel(e)) if skel(lat) and skel(e) else 0
            if sc > best[0] or (sc == best[0] and sk > best[3]):
                best = (sc, s, i, sk)
    res.append({'id': r['id'], 'rank': int(r['rank']), 'word': r['word'], 'translit': r['translit'], 'latin': lat,
                'pos': r['pos'], 'gloss': r['gloss'], 'match': best[1], 'sense_no': (best[2] + 1) if best[2] is not None else '',
                'score': round(best[0], 3), 'skeleton': round(best[3], 3)})
for x in res:
    comb = max(x['score'], 0.5 * x['score'] + 0.5 * x['skeleton'])
    x['proposed'] = 'yes' if x['score'] >= 0.85 and x['sense_no'] == 1 else ('review' if comb >= 0.7 else 'no')
json.dump(res, open(sys.argv[2], 'w'), ensure_ascii=False)

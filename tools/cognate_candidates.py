"""Usage: python tools/cognate_candidates.py languages/es/vocab.tsv out.json

Score each Spanish vocab row for transparency to an English reader: how closely the
Spanish headword resembles one of its own English gloss senses, after regular
Spanish->English spelling correspondences. Gloss-based, so false friends score low
automatically (embarazada: pregnant). The RULES table is Spanish-specific; other Romance
languages need their own. Bands used for languages/es (reviewed by hand):
yes = score >= 0.85 on the first gloss sense; review = score >= 0.70."""
import csv, os, re, sys, unicodedata, difflib, json

def strip_acc(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

# Spanish -> English-looking spelling; ordered, applied to the Spanish word
RULES = [
    (r'cion$', 'tion'), (r'ciones$', 'tions'), (r'sion$', 'sion'), (r'dad$', 'ty'), (r'tad$', 'ty'),
    (r'mente$', 'ly'), (r'oso$', 'ous'), (r'osa$', 'ous'), (r'ico$', 'ic'), (r'ica$', 'ic'),
    (r'ivo$', 'ive'), (r'iva$', 'ive'), (r'ismo$', 'ism'), (r'ista$', 'ist'), (r'ia$', 'y'),
    (r'io$', 'y'), (r'ente$', 'ent'), (r'ante$', 'ant'), (r'encia$', 'ence'), (r'ancia$', 'ance'),
    (r'izar$', 'ize'), (r'ificar$', 'ify'), (r'ar$', ''), (r'er$', ''), (r'ir$', ''),
    (r'([^aeiou])o$', r'\1'), (r'([^aeiou])a$', r'\1'), (r'([^aeiou])e$', r'\1'),
    (r'^es([ptc])', r'\1'), (r'f', 'ph'), (r'qu', 'c'), (r'z', 'c'), (r'll', 'l'), (r'ñ', 'n'), (r'j', 'g'),
]
def variants(w):
    w = strip_acc(w.lower())
    out = {w}
    v = w
    for pat, rep in RULES:
        nv = re.sub(pat, rep, v)
        if nv != v:
            v = nv; out.add(v)
    # also without the f->ph etc. (applied cumulatively above); keep a stem without final vowel
    out.add(re.sub(r'[aeo]s?$', '', w))
    return {x for x in out if x}

def senses(gloss, pos):
    out = []
    for s in re.split(r';', gloss):
        s = re.sub(r'\(.*?\)|\[.*?\]', '', s).strip().lower()
        s = re.sub(r'^.*?:\s*', '', s) if ':' in s else s     # "a través: across" -> across
        if pos == 'VERB':
            s = re.sub(r'^to\s+', '', s)
        s = re.sub(r'^(a|an|the)\s+', '', s)
        if s:
            out.append(s)
    return out

def sim(a, b):
    r = difflib.SequenceMatcher(None, a, b).ratio()
    # shared beginning matters most for recognition
    p = len(os.path.commonprefix([a, b]))
    return max(r, min(1.0, 0.5 * r + 0.5 * p / max(len(a), len(b))))

rows = list(csv.DictReader(open(sys.argv[1]), delimiter='\t'))
res = []
for r in rows:
    w, pos, gl = r['word'], r['pos'], r['gloss']
    ss = senses(gl, pos)
    best = (0, None, None)
    for i, s in enumerate(ss):
        for word_s in [s] + s.split():          # whole sense or any word in it
            if len(word_s) < 3: continue
            ws = strip_acc(word_s)
            for v in variants(w):
                sc = sim(v, ws)
                if sc > best[0]:
                    best = (sc, s, i)
    res.append({'id': r['id'], 'rank': int(r['rank']), 'word': w, 'pos': pos, 'gloss': gl,
                'match': best[1] or '', 'sense_no': (best[2] + 1) if best[2] is not None else '',
                'score': round(best[0], 3)})
for x in res:
    selfgloss = re.search(r'\((money|beverage|dance|game)', x['gloss'] or '') is not None
    x['proposed'] = ('yes' if x['score'] >= 0.85 and x['sense_no'] == 1 and not selfgloss
                     else 'review' if x['score'] >= 0.7 else 'no')
json.dump(res, open(sys.argv[2], 'w'), ensure_ascii=False)

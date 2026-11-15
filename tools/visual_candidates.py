"""Usage: python tools/visual_candidates.py languages/es/vocab.tsv out.json  (needs nltk + its wordnet corpus)

Propose which nouns can be shown in a picture, from the WordNet lexicographer file of
the first sense of the row's first English gloss."""
import csv, re, sys, json, warnings
warnings.filterwarnings("ignore")
from nltk.corpus import wordnet as wn
YES = {"noun.artifact", "noun.animal", "noun.plant", "noun.body", "noun.food", "noun.object"}
REVIEW = {"noun.person", "noun.substance", "noun.location", "noun.phenomenon", "noun.shape", "noun.event"}
def head(gloss):
    g = gloss.split(";")[0]
    g = re.sub(r"\(.*?\)|\[.*?\]", "", g).strip().lower()
    g = re.sub(r"^.*?:\s*", "", g) if ":" in g else g
    g = re.sub(r"^(a|an|the)\s+", "", g).strip()
    return g
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE))
out = []
for r in rows:
    if r["pos"] != "NOUN":
        continue
    h = head(r["gloss"])
    cands = [h, h.replace(" ", "_"), h.split()[-1] if h else ""]
    syn = next((wn.synsets(c, "n") for c in cands if c and wn.synsets(c, "n")), [])
    lex = syn[0].lexname() if syn else ""
    defn = syn[0].definition() if syn else ""
    prop = "object" if lex in YES else "review" if lex in REVIEW else "no"
    out.append({"id": r["id"], "rank": int(r["rank"]), "word": r["word"], "gloss": r["gloss"],
                "english": h, "wordnet_class": lex.replace("noun.", ""), "wordnet_sense": defn, "proposed": prop})
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False)

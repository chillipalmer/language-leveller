from language_leveller.cleaner import Cleaner

CFG = {
    "abbreviations": {"q": "que", "xq": "porque", "tb": "también"},
    "ignore_patterns": [r"\b(?:ja|je){2,}j?\b", r"\blo+l\b"],
}
KNOWN = {"hola", "leer", "carro", "que"}


def c():
    return Cleaner(CFG, known_form=lambda w: w in KNOWN)


def test_strips_internet_noise_and_records_it():
    seg = c().clean("Holaaaa @ana!!! q tal?? 😂 jajaja https://x.co/a #finde :)")
    assert seg.clean == "Hola! que tal?"
    kinds = {i["type"] for i in seg.ignored}
    assert {"mention", "emoji", "url", "hashtag", "interjection", "emoticon",
            "abbreviation", "elongation"} <= kinds
    assert "internet_text" in seg.flags


def test_elongation_uses_vocabulary():
    cl = c()
    assert cl.clean("leeeer").clean == "leer"       # keeps the double vowel the word needs
    assert cl.clean("carrrro").clean == "carro"
    assert cl.clean("bieeeen").clean == "bien"      # unknown: collapse fully


def test_html_and_lines():
    segs = c().segments("<p>Hola &amp; adiós</p><script>x=1</script><p>Otra línea</p>")
    assert [s.clean for s in segs] == ["Hola & adiós", "Otra línea"]


def test_list_markers_markdown_and_caps():
    segs = c().segments("- **Hola** amigo\n2. [mira esto](http://a.b) ya\nESTO ES UNA PRUEBA MUY IMPORTANTE")
    assert segs[0].clean == "Hola amigo"
    assert segs[1].clean == "mira esto ya"
    assert segs[2].clean == "Esto es una prueba muy importante" and "all_caps" in segs[2].flags


def test_offsets_point_into_source():
    text = "uno\n\ndos tres"
    segs = c().segments(text)
    assert [text[s.start:s.end] for s in segs] == ["uno", "dos tres"]

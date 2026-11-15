"""tools/fa_translit_convert.py: IPA-style -> single-letter Persian transliteration."""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parent.parent / "tools" / "fa_translit_convert.py"
_spec = importlib.util.spec_from_file_location("fa_translit_convert", _p)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_convert():
    c = mod.convert
    assert c("خواهر", "xɑhær") == "xāhar"
    assert c("بچه", "bæʧʧe") == "baččeh"
    assert c("موقعیت", "mowɣeʔijjæt") == "mowqe'iyyat"
    assert c("غذا", "ɣæzɑ") == "ġazā"
    assert c("تحقق", "tæhæɣɣoɣ") == "tahaqqoq"
    assert c("پیدا کردن", "pejdɑ kærdæn") == "peydā kardan"
    assert c("استفاده کردن", "estefɑde kærdæn") == "estefādeh kardan"
    assert c("نماینده مجلس", "næmɑjændeje mæʤles") == "namāyandeh-ye majles"
    assert c("راه", "rɑh") == "rāh"
    assert c("و", "væ / o") == "va / o"
    assert c("سرمایه‌گذاری", "særmɑjeɡozɑri") == "sarmāyeh-gozāri"


def test_vocab_file_is_converted():
    fa = Path(__file__).resolve().parent.parent / "languages" / "fa" / "vocab.tsv"
    text = fa.read_text(encoding="utf-8")
    assert not set("æɑʃʧʤʒɣʔɡ") & set(text)

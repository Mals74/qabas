"""الفهرس: rule-based root finding and dictionary lookup (no AI)."""
import pytest

from app import fahras

pytestmark = pytest.mark.skipif(not fahras.available(), reason="dictionary data not shipped")


@pytest.mark.parametrize("word,root", [
    ("الغُرَّة", "غرر"), ("فَيَعۡلَمُونَ", "علم"), ("المستغفرين", "غفر"), ("يخرجون", "خرج"),
    ("التوحيد", "وحد"), ("العبادة", "عبد"), ("أَوۡلِيَآءَ", "ولي"), ("بِٱلۡمَوَدَّةِ", "ودد"), ("مكتوب", "كتب"),
])
def test_root_is_among_the_candidates(word, root):
    assert root in fahras.find_roots(word)


def test_lookup_cites_the_books():
    res = fahras.lookup("الغُرَّة")
    first = res["roots"][0]
    assert first["root"] == "غرر"
    books = [e["book"] for e in first["entries"]]
    assert books[0] == "النهاية في غريب الحديث والأثر"           # غريب الحديث first
    assert all(e["text"] and e["author"] for e in first["entries"])


def test_clean_word_doubles_shadda_and_reads_madd():
    assert fahras.clean_word("مَوَدَّةِ") == "موددة"
    assert fahras.clean_word("أَوۡلِيَآءَ") == "أولياء"

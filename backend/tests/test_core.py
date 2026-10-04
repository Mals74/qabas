"""Core checks for the parts that must never be wrong.

Run from the backend folder:  python -m pytest -q
"""
from app.arabic import normalize
from app.hadith import build_query, search_link
from app.pipeline import build_segments, check_cards
from app.quran import verify


# ---------- Arabic normalization ----------

def test_normalize_unifies_letters():
    assert normalize("أَمَرَ إِلَّا آمَنَ ٱللَّهُ") == "امر الا امن الله"
    assert normalize("الصلاةُ على") == "الصلاه علي"


# ---------- Quran verification ----------

def test_verse_found_from_plain_recitation():
    m = verify("وما خلقت الجن والانس الا ليعبدون")
    assert (m.surah_name, m.ayah_from, m.verified) == ("الذاريات", 56, True)


def test_partial_quote_of_long_verse():
    m = verify("واعبدوا الله ولا تشركوا به شيئا")
    assert (m.surah, m.ayah_from) == (4, 36) and m.verified


def test_quote_spanning_two_verses():
    m = verify("الحمد لله رب العالمين الرحمن الرحيم")
    assert (m.surah, m.ayah_from, m.ayah_to) == (1, 2, 3)


def test_repeated_sentence_is_flagged():
    m = verify("ان الله لا يغفر ان يشرك به ويغفر ما دون ذلك لمن يشاء")
    assert m.ambiguous and m.surah == 4


def test_ordinary_speech_is_not_quran():
    m = verify("هذا كلام عادي ليس من القران ابدا والله المستعان")
    assert m is None or not m.verified


# ---------- review cards need evidence ----------

def test_cards_without_evidence_are_rejected():
    segs = build_segments(1, [
        {"start": 0, "end": 5, "kind": "sharh", "text": "الشرك نوعان: شرك أكبر يخرج من الملة، وشرك أصغر ينقص التوحيد"},
    ])
    ok = {"kind": "masalah", "question": "ما أنواع الشرك؟", "answer": "أكبر وأصغر",
          "evidence_quote": "الشرك نوعان: شرك أكبر يخرج من الملة", "evidence_start": 0}
    made_up = {"kind": "masalah", "question": "سؤال", "answer": "جواب",
               "evidence_quote": "وهذا كلام لم يقله الشيخ في الدرس أبدا", "evidence_start": 0}
    accepted, rejected = check_cards(1, [ok, made_up], segs)
    assert len(accepted) == 1 and rejected == 1


def test_audience_words_are_never_stored():
    segs = build_segments(1, [{"start": 0, "kind": "audience", "text": "اسمي فلان وعندي سؤال"}])
    assert "فلان" not in segs[0].text


# ---------- hadith ----------

def test_dorar_link_searches_the_sheikhs_words():
    assert search_link("إنما الأعمال").startswith("https://dorar.net/hadith/search?q=")


def test_dorar_query_keeps_spelling():
    assert build_query("مَن كانَ يُؤْمِنُ باللَّهِ") == "من كان يؤمن بالله"

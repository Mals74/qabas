"""Hadith books from fawazahmed0/hadith-api (Unlicense): download, split chain/narration, group, cite.

Used by tools/build_hadith_corpus.py; the app itself only reads the built file (data/hadith_corpus.json.gz).
"""
import re

from app.arabic import normalize

SOURCE_URL = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/ara-{book}.json"
# edition id -> how the book is cited in Arabic
BOOKS = {
    "bukhari": "صحيح البخاري",
    "muslim": "صحيح مسلم",
    "abudawud": "سنن أبي داود",
    "tirmidhi": "جامع الترمذي",
    "nasai": "سنن النسائي",
    "ibnmajah": "سنن ابن ماجه",
    "malik": "موطأ مالك",
    "nawawi": "الأربعون النووية",
    "qudsi": "الأربعون القدسية",
}
SAHIHAYN = {"bukhari", "muslim"}

# Words that pass a narration along the chain (normalized spelling)
TRANSMIT = {"حدثنا", "حدثني", "اخبرنا", "اخبرني", "انبانا", "سمعت", "عن", "وحدثنا", "وحدثني", "واخبرنا",
            "حدثناه", "حدثنيه", "اخبرناه", "سمع", "يحدث", "حدثه", "اخبره", "وحدثناه", "واخبرني",
            "واخبرناه", "وحدثنيه", "ح", "حدثنا،", "اخبرنا،"}
# Words that end the narrator's name and start the narration itself
STOP = {"قال", "قالت", "ان", "انه", "انها", "يقول", "تقول", "قالا", "قالوا", "يحدث"}
PROPHET = re.compile(r"(رسول الله|النبي|نبي الله)")

# Grades in the data are in English; shown in Arabic
_GRADE_AR = [("hasan sahih", "حسن صحيح"), ("sahih", "صحيح"), ("hasan", "حسن"), ("da'if", "ضعيف"), ("daif", "ضعيف"),
             ("da`if", "ضعيف"), ("munkar", "منكر"), ("shadh", "شاذ"), ("maudu", "موضوع"), ("mawdu", "موضوع"),
             ("maqtu", "مقطوع"), ("batil", "باطل"), ("mursal", "مرسل"), ("mauquf", "موقوف"), ("malool", "معلول")]
_GRADER_AR = {"al-albani": "الألباني", "albani": "الألباني", "zubair ali zai": "زبير علي زئي",
              "shuaib al arnaut": "شعيب الأرناؤوط", "ahmad shakir": "أحمد شاكر", "abu ghuddah": "عبد الفتاح أبو غدة",
              "muhammad muhyi al-din abdul hamid": "محمد محيي الدين عبد الحميد", "darussalam": "دار السلام",
              "muhammad fouad abd al-baqi": "محمد فؤاد عبد الباقي", "ahmad muhammad shakir": "أحمد محمد شاكر",
              "bashar awad maarouf": "بشار عواد معروف", "salim al-hilali": "سليم الهلالي"}


def split_isnad(text: str) -> tuple[str, str]:
    """(isnad, matn): the chain of narrators and the narration, split by a simple rule.

    Look only before the first mention of the Prophet (or the first quotation mark); the last transmission word
    there ('عن عائشة', 'سمعت عمر') starts the Companion's name; the matn begins at the next comma or 'قال / أن'.
    """
    words = [(m.start(), m.end(), normalize(m.group()).replace(" ", "")) for m in re.finditer(r"\S+", text)]
    limit = len(words)
    for i, (_, _, w) in enumerate(words):
        joined = w + " " + (words[i + 1][2] if i + 1 < len(words) else "")
        if PROPHET.match(joined) or '"' in text[words[i][0]:words[i][1]]:
            limit = i
            break
    last = None
    for i in range(limit):
        if words[i][2] in TRANSMIT:
            last = i
    if last is None:
        return "", text.strip()
    for j in range(last + 1, min(len(words), last + 14)):
        raw = text[words[j - 1][0]:words[j - 1][1]]
        if words[j][2] in STOP or raw.rstrip().endswith(("،", ",")):
            cut = words[j][0]
            return text[:cut].strip(), text[cut:].strip()
    return "", text.strip()


def group_of(book: str, h: dict) -> str:
    """Muslim repeats a hadith with other chains (8.01, 8.02 ...): they share Abdul-Baqi number 8."""
    if book == "muslim" and h.get("arabicnumber"):
        return f"muslim:{str(h['arabicnumber']).split('.')[0]}"
    return f"{book}:{h['hadithnumber']}"


def display_ref(book: str, h: dict) -> str:
    """How the hadith is cited in Arabic, e.g. 'صحيح البخاري (1)' or 'سنن أبي داود (3568)'."""
    if book == "muslim" and h.get("arabicnumber"):
        return f"{BOOKS[book]} ({str(h['arabicnumber']).split('.')[0]})"
    return f"{BOOKS[book]} ({h['hadithnumber']})"


def grade_of(book: str, h: dict) -> str:
    """The grading shown with the hadith: the two Sahihs need none; for the others, the graders in the data."""
    if book in SAHIHAYN:
        return "صحيح"
    parts = []
    for g in h.get("grades") or []:
        grade = str(g.get("grade", "")).strip()
        name = str(g.get("name", "")).strip()
        if not grade or grade == "-":
            continue
        low = grade.lower()
        ar = next((a for e, a in _GRADE_AR if e in low), grade)
        who = _GRADER_AR.get(name.lower(), name)
        parts.append(f"{ar} ({who})" if who else ar)
    return "؛ ".join(dict.fromkeys(parts))


def build(raw_by_book: dict) -> list[dict]:
    """One record per hadith with text, matn, normalized matn, reference and grade."""
    out = []
    for book, data in raw_by_book.items():
        for h in data["hadiths"]:
            text = (h.get("text") or "").strip()
            if not text:
                continue                                     # a few entries have no Arabic text
            isnad, matn = split_isnad(text)
            out.append({
                "id": f"{book}:{h['hadithnumber']}",
                "group": group_of(book, h),
                "book": book,
                "ref": display_ref(book, h),
                "grade": grade_of(book, h),
                "text": text,
                "matn": matn,
                "matn_norm": normalize(matn),
                # what we search: the last words of the chain (the Companion: 'عن عائشة') + the matn
                "search_text": " ".join(isnad.split()[-6:] + [matn]),
            })
    return out

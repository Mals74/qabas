"""الفهرس: the Arabic meaning of words from four classical dictionaries — no AI involved.

Data: the dictionary table of the Jawami' al-Kalim database (Offok, published free by Islamweb), public-domain classical
texts, one row per root:
    الصحاح (الجوهري) · القاموس المحيط (الفيروزآبادي) · لسان العرب (ابن منظور) · تهذيب اللغة (الأزهري)
Books on غريب الحديث are left out on purpose (the reviewer's decision): the فهرس explains the Arabic meaning of a word,
not the explanation of hadith wording. Shipped compressed (data/fahras.db.gz); unpacked to data/fahras.db and read
from disk, so it costs almost no memory. A lookup is an indexed primary-key search: O(log n) over 12,787 roots.

How a clicked word becomes a root, by rule only:
  1. remove harakat and Quranic marks, unify alif forms
  2. strip prefixes (و ف ب ك ل ال س …) and suffixes (ها هم كم نا ون ين ات ة …) in every combination
  3. from each stem, take every 3- and 4-letter subsequence whose dropped letters are "زوائد" (سألتمونيها)
  4. for weak and hamzated roots try the usual substitutions (ا → و/ي, final ى → ي/و, alif → أ, doubled 2-letter roots)
  5. keep only candidates that exist in the dictionaries, best first (fewest letters dropped)
"""
import gzip
import re
import shutil
import sqlite3
import threading
from functools import lru_cache
from itertools import combinations

from .arabic import strip_diacritics
from .config import DATA_DIR

GZ = DATA_DIR / "fahras.db.gz"
DB = DATA_DIR / "fahras.db"

# Display order: the concise dictionaries first, the large ones after
BOOKS = [
    ("sa7a7", "الصحاح", "الجوهري"),
    ("mo7eet", "القاموس المحيط", "الفيروزآبادي"),
    ("lesan", "لسان العرب", "ابن منظور"),
    ("tahzeeb", "تهذيب اللغة", "الأزهري"),
]
SOURCE = "قاعدة بيانات جوامع الكلم (شركة أفق، نشر إسلام ويب) — نصوص المعاجم في الملك العام"

_ZAWAID = set("سألتمونيهاا")                      # letters that can be added to a root
_CONJ = ["", "و", "ف"]
_PARTICLE = ["", "ب", "ك", "ل", "س", "ال", "بال", "كال", "لل"]
_VERBAL = ["", "ي", "ت", "ن", "أ", "ا", "است", "يست", "تست", "نست", "مست", "م", "مت", "ين", "ان", "ت"]
_PREFIXES = sorted({c + p + v for c in _CONJ for p in _PARTICLE for v in _VERBAL
                    if not (p.endswith("ال") or p == "لل") or v in ("", "م", "مت", "مست", "ا", "است", "ت")})
_SUFFIXES = ["", "ه", "ها", "هم", "هما", "هن", "ك", "كم", "كما", "كن", "نا", "ني", "ي", "ة", "ات", "ون", "ين", "ان", "وا", "تم", "تن",
             "ت", "تا", "ن", "ا", "تها", "اته", "اتها", "اتهم", "وه", "وها", "وهم", "ية", "يه", "يات", "يون", "يين",
             "اء", "ونك", "ونه", "ونها", "ونهم", "ونكم", "ونا", "وني", "تموه", "تموها", "تي", "اتي", "ته", "تهم"]
_lock = threading.Lock()


def _ensure_db() -> bool:
    """Unpack the dictionaries the first time they are needed. False if the data file is missing."""
    if DB.exists() and (not GZ.exists() or DB.stat().st_mtime >= GZ.stat().st_mtime):
        return True                                  # unpacked, and not older than the shipped file
    if not GZ.exists():
        return False
    with _lock:
        if not DB.exists() or DB.stat().st_mtime < GZ.stat().st_mtime:
            tmp = DB.with_suffix(".tmp")
            with gzip.open(GZ, "rb") as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            tmp.replace(DB)
    return True


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)


def _loose(s: str) -> str:
    """One spelling for comparison: hamza forms and alif maqsura unified."""
    return re.sub("[أإآءئؤ]", "ء", s).replace("ى", "ي")


@lru_cache(maxsize=1)
def _roots() -> dict:
    """{loose spelling: [roots as stored]} for every root (and for each alternative listed in a combined heading)."""
    if not _ensure_db():
        return {}
    out: dict = {}
    with _connect() as con:
        for (root,) in con.execute("SELECT root FROM dictionary"):
            if not root or len(root) > 30:              # a few rows of the source have text in the root column
                continue
            for part in re.split(r"[^ء-ي]+", root):
                if 2 <= len(part) <= 6:
                    out.setdefault(_loose(part), [])
                    if root not in out[_loose(part)]:
                        out[_loose(part)].append(root)
    return out


def clean_word(word: str) -> str:
    """Letters only: no harakat, Quranic marks, tatweel or punctuation; ٱ and آ read as ا/أ.
    A shadda doubles its letter first (مَوَدَّة → موددة), which points straight at doubled roots like ودد."""
    w = re.sub(r"([ء-ي])([\u064b-\u0650\u0652]*)\u0651", r"\1\1\2", word or "")
    w = strip_diacritics(w)
    w = re.sub(r"[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]", "", w)
    w = w.replace("ٱ", "ا")
    w = ("أ" + w[1:] if w.startswith("آ") else w).replace("آ", "ا")   # inside a word آ is a long ا (أولِيَآء)
    return re.sub(r"[^ء-ي]", "", w)


def _stems(w: str):
    """(stem, letters removed) for every prefix/suffix split that leaves at least two letters."""
    seen = set()
    for p in _PREFIXES:
        if p and not w.startswith(p):
            continue
        rest = w[len(p):]
        for s in _SUFFIXES:
            if s and not rest.endswith(s):
                continue
            stem = rest[:len(rest) - len(s)] if s else rest
            if len(stem) >= 2 and stem not in seen:
                seen.add(stem)
                yield stem, len(p) + len(s)


def _variants(c: str):
    """A candidate root and its usual weak/hamza spellings."""
    yield c
    if "ا" in c:                                   # hollow / defective: قال → قول، قيل ; دعا → دعو
        for i, ch in enumerate(c):
            if ch == "ا":
                for r in ("و", "ي", "أ"):
                    yield c[:i] + r + c[i + 1:]
    if c.endswith("ي"):
        yield c[:-1] + "و"
        yield c[:-1] + "ا"
    if c.endswith("و"):                            # defective roots are stored with و، ي or ا (عدو → عدا)
        yield c[:-1] + "ا"
        yield c[:-1] + "ي"
    if len(c) == 3 and c[1] == "ي":                # hollow with ي written: مستقيم → قوم ، نستعين → عون
        yield c[0] + "و" + c[2]
    if len(c) == 3 and c[0] == "ت":                # افتعل from و: اتقى → وقي
        yield "و" + c[1:]
    if len(c) == 2:                                # doubled: رد → ردد ; and defective: دع → دعو، دعي
        yield c + c[-1]
        yield c + "و"
        yield c + "ي"
        yield "و" + c                              # assimilated: عد → وعد
        yield c[0] + "ا" + c[1]


def find_roots(word: str, limit: int = 4) -> list[str]:
    """Roots (as stored in the dictionaries) the word may come from, best first."""
    roots = _roots()
    w = clean_word(word)
    if len(w) < 2 or not roots:
        return []
    best: dict = {}
    for stem, cut in _stems(w):
        stem = stem.replace("ى", "ي")
        for size in (3, 4, 2):
            if size > len(stem):
                continue
            for keep in combinations(range(len(stem)), size):
                dropped = [stem[i] for i in range(len(stem)) if i not in keep]
                if any(ch not in _ZAWAID for ch in dropped):
                    continue
                cand = "".join(stem[i] for i in keep)
                # root letters that look like additions; a kept alif is almost never a root letter
                kept_extra = sum(ch in _ZAWAID for ch in cand) / 2 + 3 * cand.count("ا")
                last_dropped = (len(stem) - 1) not in keep and stem[-1] not in "ةايونت"
                for v in _variants(cand):
                    for root in roots.get(_loose(v), []):
                        # fewer letters removed, fewer "added-looking" letters kept, fewer substitutions = more likely
                        score = (cut / 2 + 2 * len(dropped) + kept_extra + 2 * (v != cand) + 2 * (size == 2)
                                 + (size == 4) + 3 * last_dropped)
                        if root not in best or score < best[root]:
                            best[root] = score
    return [r for r, _ in sorted(best.items(), key=lambda x: (x[1], len(x[0])))[:limit]]


def _clean_entry(text: str) -> str:
    t = (text or "").strip().strip('"').strip()
    t = re.sub(r"\s*/\d{1,2}(?!\d)\s*", " ", t)      # the source's markers around poetry (/50 /51) and verses (/4)
    return re.sub(r"\s+", " ", t).strip()


def entries(root: str, cut: int = 0) -> list[dict]:
    """Every dictionary's entry for this root, in BOOKS order, skipping empty ones."""
    if not _ensure_db():
        return []
    with _connect() as con:
        row = con.execute("SELECT * FROM dictionary WHERE root = ?", (root,)).fetchone()
        cols = [d[0] for d in con.execute("SELECT * FROM dictionary LIMIT 0").description]
    if not row:
        return []
    data = dict(zip(cols, row))
    out = []
    for key, title, author in BOOKS:
        text = _clean_entry(data.get(key))
        if text:
            short = bool(cut) and len(text) > cut
            out.append({"key": key, "book": title, "author": author, "entry": root.strip('"'),
                        "text": text[:cut].rsplit(" ", 1)[0] + " …" if short else text, "more": short})
    return out


def lookup(word: str) -> dict:
    """The clicked word -> its likely roots, each with the dictionaries' entries."""
    found = find_roots(word)
    return {"word": clean_word(word), "source": SOURCE,
            "roots": [{"root": r.strip('"'), "key": r, "entries": entries(r, cut=1200)} for r in found]}


def browse(prefix: str, limit: int = 30) -> list[str]:
    """Roots that start with these letters (for the search box)."""
    p = _loose(clean_word(prefix))
    if not p:
        return []
    keys = sorted(k for k in _roots() if k.startswith(p))
    out = []
    for k in keys:
        for r in _roots()[k]:
            if r not in out:
                out.append(r)
    return out[:limit]


def available() -> bool:
    return GZ.exists() or DB.exists()

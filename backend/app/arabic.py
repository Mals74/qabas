"""Arabic text normalization used for matching (never for display).

We only normalize copies of the text to compare them. What the user sees is
always the original: the verified Uthmani verse, or the sheikh's exact words.
"""
import re

# Harakat, Quranic annotation marks, small high letters, tatweel
_DIACRITICS = re.compile(
    "[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]"
)
# Alef forms: hamza above/below, madda, wasla -> bare alef
_ALEF = re.compile("[آأإٱٲٳ]")
# Anything that isn't an Arabic letter, digit or space
_NON_LETTERS = re.compile("[^ء-ي0-9\\s]")
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Strip diacritics and unify letter variants so different spellings compare equal.

    Steps (as described in the project brief):
    - remove tashkeel and Quranic marks
    - unify alef forms (أ إ آ ٱ -> ا)
    - unify alef maqsura and ya (ى -> ي), ta marbuta -> ha (ة -> ه)
    - unify hamza seats (ؤ -> و, ئ -> ي)
    """
    if not text:
        return ""
    t = _DIACRITICS.sub("", text)          # drop harakat and marks
    t = _ALEF.sub("ا", t)                  # unify alef forms
    t = t.replace("ى", "ي")                # alef maqsura -> ya
    t = t.replace("ة", "ه")                # ta marbuta -> ha
    t = t.replace("ؤ", "و").replace("ئ", "ي")  # hamza seats
    t = t.replace("ء", "")                 # standalone hamza is written inconsistently; drop it
    t = re.sub(r"ي{2,}", "ي", t)            # شيئا -> شييا -> شيا (matches Uthmani شَيۡـٔٗا)
    t = _NON_LETTERS.sub(" ", t)           # punctuation, brackets ﴿﴾, Quranic symbols -> space
    return _SPACES.sub(" ", t).strip()


def strip_diacritics(text: str) -> str:
    """Remove harakat and punctuation only, keeping the letters as written.

    Used for external searches (Dorar), which expect normal spelling (يؤمن, not يومن).
    """
    t = _DIACRITICS.sub("", text or "")
    t = _NON_LETTERS.sub(" ", t)
    return _SPACES.sub(" ", t).strip()


def uthmani_variants(text: str) -> list[str]:
    """Normalized forms of an Uthmani verse.

    Uthmani script writes some words differently from everyday spelling,
    e.g. ٱلصَّلَوٰةَ vs الصلاة, ٱلرَّحۡمَٰنِ vs الرحمن. The dagger alef (ٰ)
    is sometimes pronounced as a full alef, so we index two versions:
    one that drops it and one that turns it into ا.
    """
    plain = normalize(text)
    with_alef = normalize(text.replace("ٰ", "ا"))
    # Common Uthmani spellings of ـوٰة / ـوٰا (صلوة, زكوة, حيوة) -> everyday ـاة
    everyday = re.sub(r"وا?ه\b", "اه", with_alef)
    return list(dict.fromkeys([plain, with_alef, everyday]))  # unique, order kept

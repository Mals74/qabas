"""Quran verification.

The AI transcribes what the sheikh recited, but we never display the AI's
version of a verse. Instead we look the recitation up in the authoritative
Uthmani text (Madinah Mushaf script) and show that, with surah and ayah.
If no confident match exists, the segment is shown as "unverified".
"""
import json
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import Optional

from rapidfuzz import fuzz, process

from .arabic import normalize, uthmani_variants
from .config import DATA_DIR, QURAN_MATCH_THRESHOLD

# Text file shipped with the app: [{"s": surah_no, "name": "...", "verses": ["...", ...]}]
QURAN_FILE = DATA_DIR / "quran_uthmani.json"

# The text we DISPLAY: the King Fahd Complex's official digital Mushaf data (UthmanicHafs v2.0, downloaded from
# download.qurancomplex.gov.sa), copied as is, with its own ayah-number symbols, shown in the Complex's own font
# (frontend/public/fonts/uthmanic_hafs_v20.ttf). {"ayat": {"113:4": "…"}}. The file above is only for matching.
MUSHAF_FILE = DATA_DIR / "quran_kfgqpc.json"

# Where the text comes from, shown in the UI next to every verified verse
QURAN_SOURCE_LABEL = "مصحف المدينة النبوية - نص مجمع الملك فهد لطباعة المصحف الشريف"


@dataclass
class Match:
    surah: int
    surah_name: str
    ayah_from: int
    ayah_to: int
    text: str            # authoritative Uthmani text (what we display)
    score: float         # 0-100 fuzzy score
    verified: bool       # the words are Quran (score >= threshold)
    ambiguous: bool = False  # the quoted words occur in more than one place
    also_in: list = None     # other places they occur, e.g. ["النساء: 48"]
    source: str = QURAN_SOURCE_LABEL
    parts: list = None       # a quote joining verses from different places, e.g. الفلق 1 + الناس 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@lru_cache(maxsize=1)
def _index():
    """Build the search index once: every verse plus runs of 2-3 consecutive verses.

    Runs let us match a recitation that spans more than one ayah.
    Returns (keys, meta) where keys[i] is a normalized string and meta[i]
    describes which verse(s) it came from.
    """
    data = json.loads(QURAN_FILE.read_text(encoding="utf-8"))
    keys, meta = [], []
    for surah in data:
        verses = surah["verses"]
        for i in range(len(verses)):
            for span in (1, 2, 3):
                if i + span > len(verses):
                    break
                text = " ".join(verses[i:i + span])
                for variant in uthmani_variants(text):
                    keys.append(variant)
                    meta.append((surah["s"], surah["name"], i + 1, i + span, text))
    return keys, meta


@lru_cache(maxsize=1)
def _mushaf():
    ayat = json.loads(MUSHAF_FILE.read_text(encoding="utf-8"))["ayat"]
    names = {x["name"]: x["s"] for x in json.loads(QURAN_FILE.read_text(encoding="utf-8"))}
    return ayat, names


def mushaf_text(surah, ayah_from: int, ayah_to: int) -> str:
    """The King Fahd Complex text of these verses, with waqf marks and ayah numbers (surah = number or name)."""
    ayat, names = _mushaf()
    s = surah if isinstance(surah, int) else names.get(surah)
    return " ".join(ayat[f"{s}:{a}"] for a in range(ayah_from, ayah_to + 1) if f"{s}:{a}" in ayat)


def verify(recited: str) -> Optional[Match]:
    """Find the verse(s) the sheikh recited. Returns None for very short input.

    A quote that joins verses from two places ("قل أعوذ برب الفلق وقل أعوذ برب الناس") does not match any one
    place well; then we try splitting it at a word starting with و and verify each half on its own.
    """
    m = _verify_one(recited)
    if m and m.verified:
        return m
    joined = _verify_split(recited)
    return joined or m


def _verify_split(recited: str) -> Optional[Match]:
    words = recited.split()
    best = None
    for i in range(2, len(words) - 1):
        w = normalize(words[i])
        if not w.startswith("و") or len(w) < 3:
            continue
        left = _verify_one(" ".join(words[:i]))
        right = _verify_one(" ".join([words[i][1:]] + words[i + 1:]))
        if left and right and left.verified and right.verified and not _overlaps(
                (left.surah, left.surah_name, left.ayah_from, left.ayah_to),
                (right.surah, right.surah_name, right.ayah_from, right.ayah_to)):
            score = min(left.score, right.score)
            if not best or score > best.score:
                best = Match(surah=left.surah, surah_name=left.surah_name, ayah_from=left.ayah_from,
                             ayah_to=left.ayah_to, text=left.text, score=score, verified=True, also_in=[],
                             parts=[{"surah": x.surah, "surah_name": x.surah_name, "ayah_from": x.ayah_from, "ayah_to": x.ayah_to,
                                     "text": x.text} for x in (left, right)])
    return best


def _verify_one(recited: str) -> Optional[Match]:
    query = normalize(recited)
    if len(query) < 8:                      # too short to identify reliably
        return None
    keys, meta = _index()

    # Stage 1: fast shortlist with partial_ratio (query can be part of a verse)
    shortlist = process.extract(query, keys, scorer=fuzz.partial_ratio, limit=400)

    # Keep the best-scoring variant per verse range
    per_range: dict = {}
    for key, _, i in shortlist:
        rng = meta[i][:4]                       # (surah, name, from, to)
        confidence = _confidence(query, key)
        closeness = abs(len(key) - len(query))  # how close the lengths are
        if rng not in per_range or confidence > per_range[rng][0]:
            per_range[rng] = (confidence, closeness, i)
    if not per_range:
        return None

    # Stage 2: highest confidence wins; among (near) ties, pick the range whose
    # length is closest to what was recited (a 2-verse quote -> the 2-verse run,
    # a partial quote of one long verse -> that verse).
    top = max(c for c, _, _ in per_range.values())
    tied = [v for v in per_range.values() if v[0] >= top - 2]
    confidence, _, best = min(tied, key=lambda v: v[1])

    surah, name, a_from, a_to, text = meta[best]
    # Ambiguous: a *different* single verse contains the quote equally well
    # (e.g. النساء 48 and 116 share the same sentence)
    alternatives = []
    for (s_no, s_name, f, t), (c, _, _) in per_range.items():
        if f == t and c >= max(QURAN_MATCH_THRESHOLD, confidence - 4) and not _overlaps((s_no, s_name, f, t), meta[best]):
            alternatives.append((s_name, f, t))
    ambiguous = bool(alternatives)
    return Match(
        surah=surah, surah_name=name, ayah_from=a_from, ayah_to=a_to,
        text=text, score=round(confidence, 1),
        verified=confidence >= QURAN_MATCH_THRESHOLD,
        ambiguous=ambiguous,
        also_in=[f"{n}: {a}" for n, a, _ in alternatives[:3]],
    )


def _confidence(query: str, key: str) -> float:
    """How sure we are that `query` is (part of) `key`.

    partial_ratio answers "is the query contained in the verse?". It must not be
    used when the verse is much shorter than the query, otherwise a short verse
    like الٓمٓ would "match" any sentence containing الم.
    """
    if len(key) < 0.9 * len(query):
        return fuzz.ratio(query, key)
    return fuzz.partial_ratio(query, key)


def _overlaps(a, b) -> bool:
    """True if two index entries share a surah and overlapping ayah ranges."""
    return a[0] == b[0] and a[2] <= b[3] and b[2] <= a[3]


def reference_label(m: Match) -> str:
    """e.g. [البينة: 5] or [الذاريات: 56-57]."""
    ayah = f"{m.ayah_from}" if m.ayah_from == m.ayah_to else f"{m.ayah_from}-{m.ayah_to}"
    return f"[{m.surah_name}: {ayah}]"

"""Hadith takhrij: finding the full hadith (with its reference and grade) for the words the sheikh said.

Order of work (see hadith_index.py for the first two steps):
  1. Haystack BM25 over nine hadith books -> 12 candidates
  2. quote rule: 5+ consecutive words of the quote inside the top candidate -> accepted, no AI call
  3. otherwise the light Gemini model reads the candidates and picks one or says "none"
If the check cannot run (no key, quota), the top candidates are shown clearly marked as unconfirmed.
Every result also carries a link to the same search on Dorar (الدرر السنية), for the student to verify it there:
Dorar's own interface refuses requests from other servers and sites, so we link to it instead of calling it.

Rule (from the challenge's scientific standard): a hadith is never shown without its reference, and we never
generate hadith text ourselves: every text shown is the book's own.
"""
import re
from urllib.parse import quote

from . import hadith_index
from .arabic import normalize, strip_diacritics
from .config import HADITH_PER_REQUEST

# Words that introduce a quote rather than belong to it ("قال عليه الصلاة والسلام: …")
_LEAD = {"قال", "فقال", "وقال", "يقول", "قوله", "حديث", "والله", "قالت", "فقالت", "عليه", "الصلاة", "والسلام",
         "صلى", "وسلم", "وفي", "رواية", "لفظ"}
_HONORIFIC = re.compile(r"صلي الله عليه وسلم|رضي الله عنهما|رضي الله عنها|رضي الله عنهم|رضي الله عنه|عليه السلام")


def _core_words(fragment: str) -> list[str]:
    """The quote's words without harakat, honorifics and the words that only introduce it."""
    words = _HONORIFIC.sub(" ", strip_diacritics(fragment)).split()
    words = [w for w in (re.sub(r"[^ء-ي]", "", w) for w in words) if w]
    lead = {normalize(x) for x in _LEAD}
    while len(words) > 3 and normalize(words[0]) in lead:
        words.pop(0)
    return words


def build_query(fragment: str, max_words: int = 7) -> str:
    """A short, distinctive run of the sheikh's words (for the Dorar link and for display)."""
    return " ".join(_core_words(fragment)[:max_words])


def search_link(query: str) -> str:
    """The same search on dorar.net, so the student can always check it there."""
    return f"https://dorar.net/hadith/search?q={quote(query)}"


def _from_books(idx, group: str, method: str) -> dict:
    """A hadith taken from the text of the book itself, with its reference and grade."""
    info = idx.info(group)
    return {"text": info["text"], "narrator": "", "muhaddith": "", "source": info["ref"], "number": "",
            "grade": info.get("grade", ""), "origin": "books", "method": method, "group": group}


def _candidate_line(idx, group: str) -> str:
    """One candidate as the check sees it: the reference and the fullest wording, without harakat."""
    info = idx.info(group)
    return f"[{info['ref']}] " + " ".join(strip_diacritics(info["text"]).split()[:70])


def takhrij_many(items: list[tuple[str, str]], provider=None) -> dict[str, dict]:
    """Full hadith for several quotes at once: items = [(id, fragment)] -> {id: result}.

    Result: {"ok", "query", "results": [{text, source, grade, origin, method, …}], "search_url", "message", "method"}
    where method is rule (5 consecutive words matched) | check (AI picked it from the candidates)
    | candidate (unconfirmed) | none (not found in these books).
    """
    idx = hadith_index.get_index()
    out: dict[str, dict] = {}
    pending: list[dict] = []                                   # quotes that need the AI check
    for key, fragment in items:
        query = build_query(fragment)
        base = {"ok": True, "query": query, "results": [], "search_url": search_link(query), "message": ""}
        if len(_core_words(fragment)) < 2:                    # «حديث الإفك» (two words) is a valid reference
            out[key] = dict(base, ok=False, message="العبارة قصيرة جدًا للبحث", method="none")
            continue
        cands = idx.candidates(fragment) if idx else []
        if cands and idx.quote_rule(fragment, cands[0]):
            out[key] = dict(base, results=[_from_books(idx, cands[0], "rule")], method="rule")
        elif cands:
            pending.append({"key": key, "fragment": fragment, "base": base, "cands": cands})
        else:
            out[key] = dict(base, method="none", message="لم يُعثر عليه في كتب الحديث المتاحة؛ ابحث عنه في الدرر السنية.")

    picks: dict[str, list[int]] = {}
    can_check = provider is not None and hasattr(provider, "pick_hadith")
    if pending and can_check:
        for i in range(0, len(pending), HADITH_PER_REQUEST):
            group = pending[i:i + HADITH_PER_REQUEST]
            try:
                # numbered 1..n inside each request: the model echoes short numbers reliably, not our segment ids
                answer = provider.pick_hadith([
                    {"id": str(n), "query": p["fragment"], "candidates": [_candidate_line(idx, g) for g in p["cands"]]}
                    for n, p in enumerate(group, 1)])
                for qid, matches in (answer or {}).items():
                    m = re.search(r"\d+", str(qid))
                    if m and 1 <= int(m.group()) <= len(group):
                        picks[group[int(m.group()) - 1]["key"]] = [int(x) for x in matches if str(x).isdigit()]
                if not any(p["key"] in picks for p in group):
                    print(f"[hadith] check returned no usable answer: {str(answer)[:120]}", flush=True)
            except Exception as e:                             # quota, busy servers: those quotes stay unconfirmed
                print(f"[hadith] check failed: {str(e)[:120]}", flush=True)
    for p in pending:
        key, cands = p["key"], p["cands"]
        if key in picks:
            chosen = [cands[n - 1] for n in picks[key] if 1 <= n <= len(cands)]
            if chosen:                                          # the check found it
                out[key] = dict(p["base"], results=[_from_books(idx, chosen[0], "check")], method="check")
            else:                                               # none of the candidates is the hadith the sheikh meant
                out[key] = dict(p["base"], method="none",
                                message="لم يُعثر عليه في كتب الحديث المتاحة في التطبيق؛ ابحث عنه في الدرر السنية.")
        else:                                                   # the check could not run: show the closest, marked
            out[key] = dict(p["base"], results=[_from_books(idx, g, "candidate") for g in cands[:3]], method="candidate",
                            message="لم يُتأكد من المطابقة: هذه أقرب الأحاديث لكلام الشيخ، فراجعها.")
    return out


# ---------------- «وفي رواية: …» — a variant wording of the hadith the sheikh just quoted ----------------
# Sheikhs often quote a famous hadith and then list its wordings: «إنما الأعمال بالنيات … وفي رواية: بالنية».
# The variant alone («بالنية») is too short to search. We rebuild the full wording by putting the variant word in place
# of the closest word of the previous hadith («إنما الأعمال بالنية»), then accept only a hadith whose text contains
# that wording word for word — no AI involved.

_VARIANT_MARK = re.compile(r"^\W*(?:و\s*)?(?:في|فى)\s+(?:رواية|روايه|لفظ)(?:\s+(?:أخرى|اخرى|لمسلم|للبخاري|عند\s+\S+))?\s*[:：،,]?\s*")
_BOOK_ORDER = ["bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah", "malik", "nawawi", "qudsi"]


def says_variant(text: str) -> bool:
    """The sheikh said «وفي رواية / وفي لفظ» himself."""
    return bool(_VARIANT_MARK.match(strip_diacritics(text or "").strip()))


def keep_variant(result: dict, fragment: str) -> bool:
    """Use the variant result, or search the quote on its own? A short quote that was not found as a wording of the
    previous hadith may be a hadith of its own (e.g. «حديث الإفك»), unless the sheikh said «وفي رواية»."""
    return result["method"] == "variant" or says_variant(fragment) or len(_core_words(fragment)) < 2


def is_variant_marker(text: str) -> bool:
    """A line that only says «وفي رواية:» (the wording itself follows in the next line)."""
    rest = _VARIANT_MARK.sub("", strip_diacritics(text or "").strip(), count=1)
    return bool(_VARIANT_MARK.match(strip_diacritics(text or "").strip())) and len(re.sub(r"[^ء-ي]", "", rest)) == 0


def needs_previous(fragment: str) -> bool:
    """Too short to find on its own, or explicitly «وفي رواية …»: read it as a wording of the previous hadith."""
    plain = strip_diacritics(fragment or "").strip()
    return len(_core_words(fragment)) < 3 or bool(_VARIANT_MARK.match(plain))


def variant_phrase(previous: str, fragment: str) -> tuple[list[str], set[int]]:
    """The previous hadith's words with the variant put in place of the word(s) it replaces,
    and the positions of the variant's own words in it (every search must keep at least one of them)."""
    from rapidfuzz import fuzz
    base = _core_words(previous)
    var = _core_words(_VARIANT_MARK.sub("", strip_diacritics(fragment or "").strip(), count=1))
    if not base or len(var) >= 3:                      # nothing to build on, or a full wording of its own
        return var, set(range(len(var)))
    words, at = list(base), []
    for v in var:
        scores = [fuzz.ratio(normalize(w), normalize(v)) for w in words]
        j = max(range(len(words)), key=scores.__getitem__)
        if scores[j] >= 55:
            words[j] = v
            at.append(j)
        else:                                          # nothing it replaces: the variant adds to the hadith
            words.append(v)
            at.append(len(words) - 1)
    lo, hi = max(0, min(at) - 3), min(len(words), max(at) + 4)
    return words[lo:hi], {j - lo for j in at}


def takhrij_variant(previous: str, fragment: str) -> dict:
    """Find the hadith with this wording. method = variant (found word for word) | none."""
    idx = hadith_index.get_index()
    words, keep = variant_phrase(previous, fragment)
    phrase = " ".join(words)
    prev_q = build_query(previous)
    base = {"ok": True, "query": phrase, "results": [], "search_url": search_link(phrase or prev_q),
            "variant_of": prev_q}
    if len(words) < 2 or not idx:
        return dict(base, method="none", message="رواية أخرى للحديث السابق؛ ابحث عن لفظها في الدرر السنية.")
    # the full rebuilt wording first, then shorter windows (two words at least) that still hold the variant's words
    tries = [(0, len(words))] + [(i, i + n) for n in range(len(words) - 1, 1, -1) for i in range(len(words) - n + 1)]
    for a, b in tries:
        if not any(a <= j < b for j in keep):
            continue
        t = words[a:b]
        want = hadith_index.prep(" ".join(t))
        hits = [g for g in idx.candidates(" ".join(t), k=40) if want in hadith_index.prep(idx.info(g)["text"])]
        if hits:
            hits.sort(key=lambda g: _BOOK_ORDER.index(g.split(":")[0]) if g.split(":")[0] in _BOOK_ORDER else 99)
            found = " ".join(t)
            return dict(base, query=found, search_url=search_link(found), method="variant",
                        results=[_from_books(idx, hits[0], "variant")],
                        message=f"رواية أخرى للحديث السابق («{prev_q}») بلفظ «{found}»؛ وردت بهذا اللفظ في الكتاب.")
    return dict(base, method="none",
                message=f"رواية أخرى للحديث السابق («{prev_q}») بلفظ «{phrase}»؛ لم نجد هذا اللفظ بعينه في الكتب "
                        "المتاحة، فابحث عنه في الدرر السنية.")


def takhrij(fragment: str, provider=None) -> dict:
    """Search for a hadith the sheikh quoted (possibly partially or by meaning). See takhrij_many."""
    return takhrij_many([("1", fragment)], provider)["1"]

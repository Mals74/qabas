# ---- Qabas eval v2: text cleanup, scoring, auto-trim, negation check (tested offline) ----
import re                                            # regular expressions
from collections import Counter                      # counting word swaps
from urllib.parse import urljoin                     # make relative mp3 links absolute
import jiwer                                         # WER/CER and word alignment

# Honorific symbols are written as one glyph but spoken as words: expand before comparing
HONORIFICS = {"ﷺ": " صلى الله عليه وسلم ", "ؐ": " صلى الله عليه وسلم ", "ﷻ": " جل جلاله ",
              "ؑ": " عليه السلام ", "ؒ": " رحمه الله ", "ؓ": " رضي الله عنه ", "ؔ": " "}
_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]")
_ALEF = re.compile("[آأإٱٲٳ]")   # أ إ آ ٱ -> ا
_NON_LETTERS = re.compile("[^ء-ي\\s]")              # anything that isn't an Arabic letter (digits too)
_SPACES = re.compile(r"\s+")


NUM = "ظظظ"                                          # placeholder token for any number
_DIGITS = re.compile("[0-9\u0660-\u0669\u06F0-\u06F9]+(?:[.,/][0-9\u0660-\u0669]+)*")
_ARL = "[\u0621-\u064A]"                              # one Arabic letter (for word edges)
# Spoken number words (normalized spelling), with an optional و: collapsed to NUM so "590" = "تسعين وخمسمايه"
_NUMW = ("واحد|واحده|احدي|اثنين|اثنان|اثنتين|اثنتان|ثنتين|ثلاث|ثلاثه|ثلاثين|ثلاثون|اربع|اربعه|اربعين|اربعون|"
         "خمس|خمسه|خمسين|خمسون|سته|ستين|ستون|سبعه|سبعين|سبعون|ثمان|ثماني|ثمانيه|ثمانين|ثمانون|تسع|تسعه|تسعين|تسعون|"
         "عشر|عشره|عشرين|عشرون|مايه|ميه|مايتين|ميتين|الف|الفين|الاف|"
         "ثلاثمايه|اربعمايه|خمسمايه|ستمايه|سبعمايه|ثمانمايه|تسعمايه|" + NUM)
_NUMRUN = re.compile(r"(?<!\S)(?:و?(?:%s))(?:\s+و?(?:%s))*(?!\S)" % (_NUMW, _NUMW))
# Honorific phrases: official transcripts add or drop them freely, so they are left out of scoring
_HONOR_PHRASES = re.compile(r"(?<!\S)(صلي الله عليه وسلم|عليه الصلاه والسلام|عليه السلام|عليهم السلام|"
                            r"رضي الله عنه|رضي الله عنها|رضي الله عنهما|رضي الله عنهم|رحمه الله|رحمهم الله|"
                            r"رحمهما الله|رحمها الله|جل جلاله|عز وجل|سبحانه وتعالي|تبارك وتعالي)(?: تعالي)?(?!\S)")


def normalize(text: str) -> str:
    """Comparable form: no harakat, unified letters, no punctuation, numbers and honorifics unified."""
    t = text or ""
    for sym, words in HONORIFICS.items():            # ﷺ -> صلى الله عليه وسلم
        t = t.replace(sym, words)
    t = _DIGITS.sub(f" {NUM} ", t)                   # 590 -> NUM (spoken as words in the audio)
    t = _DIACRITICS.sub("", t)                       # drop harakat and marks
    t = _ALEF.sub("ا", t)                            # unify alef forms
    t = t.replace("ى", "ي").replace("ة", "ه")        # alef maqsura, ta marbuta
    t = re.sub(rf"(?<!{_ARL})([وفبل]{{0,2}})ماء(?!{_ARL})", r"\1ماا", t)   # ماء (water) must not become ما (negation)
    t = t.replace("ؤ", "و").replace("ئ", "ي").replace("ء", "")   # hamza seats
    t = re.sub(r"ي{2,}", "ي", t)                     # شيئا -> شيا
    t = _NON_LETTERS.sub(" ", t)                     # punctuation, Latin -> space
    t = _SPACES.sub(" ", t)
    t = re.sub(r"(?<!\S)ان لا(?!\S)", "الا", t)       # أن لا = ألا (same words, two spellings)
    t = re.sub(r"(?<!\S)(و?)عبد(ال)", r"\1عبد \2", t)   # عبدالله -> عبد الله
    t = re.sub(r"(?<!\S)(و?)ابن(?!\S)", r"\1بن", t)     # ابن / بن in names: one spelling
    t = _HONOR_PHRASES.sub(" ", t)                   # drop honorific phrases
    t = _NUMRUN.sub(NUM, t)                          # تسعين وخمسمايه -> NUM
    t = re.sub(r"(?<!\S)ه(?!\S)", " ", t)           # the hijri mark هـ after a year
    return _SPACES.sub(" ", t).strip()


def wer_cer(reference: str, hypothesis: str) -> dict:
    """Word and letter error rates on normalized text."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    return {"WER": jiwer.wer(ref, hyp), "CER": jiwer.cer(ref.replace(" ", ""), hyp.replace(" ", ""))}


# ---------------- pages: find the mp3 and the transcript ----------------
_AR = re.compile("[ء-ي]")                  # Arabic letters, to find the transcript block
_LABEL = re.compile(r"(?m)^\s*(المقدم|الشيخ|القارئ|الطالب|السائل|المذيع|طالب|سائل|س|ج)\s*[:：]\s*")


def find_mp3(html: str, page_url: str) -> str:
    """First .mp3 link in the page, made absolute."""
    m = re.search(r"""["']([^"'<>]+?\.mp3)["']""", html, re.I)
    return urljoin(page_url, m.group(1).strip()) if m else ""


def main_text(html: str) -> str:
    """Walk down from <body> into the child holding >=90% of the Arabic text; that is the transcript."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        t.decompose()                                 # drop page furniture
    count = lambda el: len(_AR.findall(el.get_text(" ")))
    node = soup.body or soup
    while True:
        kids = [c for c in node.find_all(recursive=False) if getattr(c, "name", None)]
        if not kids:
            break
        best = max(kids, key=count)
        if count(best) >= 0.9 * count(node):          # nearly all the text is inside this child
            node = best
        else:
            break                                     # text is spread over several children: stop here
    return node.get_text("\n")


def clean_reference(text: str) -> str:
    """Remove things written in the transcript but never spoken."""
    t = _LABEL.sub(" ", text)                         # speaker labels: المقدم: / الشيخ: / س: ...
    t = re.sub(r"\[[^\]]{0,120}\]", " ", t)           # [البقرة:255], [1]: references, not speech
    t = re.sub(r"\(\s*[\d٠-٩]+\s*\)", " ", t)   # footnote markers (1)
    t = re.sub(r"(?m)^\s*[\(\[]?[\d٠-٩]+[\)\]]?\s*[-–:.)].*$", " ", t)   # footnote lines at the end
    return _SPACES.sub(" ", t).strip()


# ---------------- auto-trim: compare only the part both texts cover ----------------
def _runs(alignments, min_run):
    """Aligned 'equal' blocks at least min_run words long."""
    return [c for c in alignments if c.type == "equal" and c.ref_end_idx - c.ref_start_idx >= min_run]


def auto_trim(reference: str, hypothesis: str, min_run: int = 4, slack: float = 1.6) -> tuple:
    """Cut both texts to the span they share (reference is a whole lesson, audio is 10 minutes).

    Returns (ref_trimmed, hyp_trimmed, info) using normalized words.
    """
    R, H = normalize(reference).split(), normalize(hypothesis).split()
    R = R[: int(len(H) * slack) + 200]                # the clip starts at 0: the match lies near the start
    out = jiwer.process_words(" ".join(R), " ".join(H))
    runs = _runs(out.alignments[0], min_run)
    if not runs:                                      # nothing matched: wrong page or wrong audio
        return " ".join(R), " ".join(H), {"ok": False}
    r0, r1 = runs[0].ref_start_idx, runs[-1].ref_end_idx
    h0, h1 = runs[0].hyp_start_idx, runs[-1].hyp_end_idx
    info = {"ok": True, "ref_used": r1 - r0, "ref_cut_start": r0, "hyp_cut_start": h0,
            "hyp_cut_end": len(H) - h1, "hyp_words": len(H)}
    return " ".join(R[r0:r1]), " ".join(H[h0:h1]), info


# ---------------- negations ----------------
NEGATIONS = {"لا", "لم", "لن", "ما", "ليس", "ليست", "ليسوا", "لست", "لسنا", "لستم",
             "غير", "الا", "بلا", "دون", "كلا", "لولا"}


def is_negation(w: str) -> bool:
    """Negation word, also with a و / ف prefix (ولا، فلم، وما)."""
    return w in NEGATIONS or (len(w) > 2 and w[0] in "وف" and w[1:] in NEGATIONS)


def diff_spots(a_text: str, b_text: str, ctx: int = 8, negation_only: bool = True) -> list:
    """Places where A and B differ (merged runs); by default only those involving a negation.

    Texts should already be normalized (or will be).
    """
    A, B = normalize(a_text).split(), normalize(b_text).split()
    groups, cur = [], []
    for c in jiwer.process_words(" ".join(A), " ".join(B)).alignments[0]:
        if c.type == "equal":
            if cur:
                groups.append(cur); cur = []
        else:
            cur.append(c)
    if cur:
        groups.append(cur)
    spots = []
    for g in groups:
        a0, a1 = g[0].ref_start_idx, g[-1].ref_end_idx
        b0, b1 = g[0].hyp_start_idx, g[-1].hyp_end_idx
        if negation_only:
            if not any(is_negation(w) for w in A[a0:a1] + B[b0:b1]):
                continue                              # no negation involved
            strip = lambda ws: [w[1:] if len(w) > 2 and w[0] in "وف" else w for w in ws]
            if strip(A[a0:a1]) == strip(B[b0:b1]):
                continue                              # only a و / ف prefix differs (لم / فلم): same meaning
        spots.append({"id": len(spots) + 1, "a_idx": (a0, a1), "b_words": B[b0:b1],
                      "before": " ".join(A[max(0, a0 - ctx):a0]), "after": " ".join(A[a1:a1 + ctx]),
                      "A": " ".join(A[a0:a1]) or "(لا شيء)", "B": " ".join(B[b0:b1]) or "(لا شيء)",
                      "pos": (a0 + a1) / 2 / max(len(A), 1)})
    return spots


def apply_verdicts(a_text: str, spots: list, verdicts: dict) -> str:
    """Patch A with the verdicts, from the end backwards so indexes stay valid."""
    A = normalize(a_text).split()
    for s in sorted(spots, key=lambda s: s["a_idx"][0], reverse=True):
        v = verdicts.get(s["id"], {})
        if v.get("choice") == "B":
            new = s["b_words"]
        elif v.get("choice") == "other" and v.get("heard", "").strip():
            new = normalize(v["heard"]).split()
        else:
            continue                                  # A confirmed or unsure: keep A
        A[s["a_idx"][0]:s["a_idx"][1]] = new
    return " ".join(A)


def top_substitutions(reference: str, hypothesis: str, n: int = 15) -> list:
    """Most frequent word swaps (reference -> model)."""
    out = jiwer.process_words(normalize(reference), normalize(hypothesis))
    pairs, R, H = Counter(), out.references[0], out.hypotheses[0]
    for c in out.alignments[0]:
        if c.type == "substitute":
            for i, j in zip(range(c.ref_start_idx, c.ref_end_idx), range(c.hyp_start_idx, c.hyp_end_idx)):
                pairs[(R[i], H[j])] += 1
    return pairs.most_common(n)


# ---------------- names and terms ----------------
def _term_pattern(term: str) -> re.Pattern:
    """Find a term even with attached prefixes: و ف ب ك ل (وابن، كالبهوتي، للمختصر)."""
    t = normalize(term)
    forms = [r"[وفبكل]{0,2}" + re.escape(t)]
    if t.startswith("ال"):                              # ل + ال merges into لل
        forms.append(r"[وف]?لل" + re.escape(t[2:]))
    return re.compile(r"(?<!\S)(?:" + "|".join(forms) + r")(?!\S)")


def term_scores(reference: str, hypothesis: str, terms: list) -> dict:
    """Share of name/term occurrences in the reference that the model reproduced (min(ref, hyp) per term)."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    got, total, missed = 0, 0, []
    for term in dict.fromkeys(t for t in terms if normalize(t)):   # unique, non-empty
        pat = _term_pattern(term)
        r = len(pat.findall(ref))
        if r == 0:
            continue                                     # not in this clip: not scored
        h = len(pat.findall(hyp))
        total += r; got += min(r, h)
        if h < r:
            missed.append(f"{term} ({h}/{r})")
    return {"terms_pct": got / total if total else float("nan"), "terms_total": total, "missed_terms": missed}


def raw_span(reference: str, hypothesis: str, margin: int = 25) -> str:
    """The original (un-normalized) reference text that matches the audio clip, for building a glossary."""
    _, _, info = auto_trim(reference, hypothesis)
    if not info.get("ok"):
        return ""
    R = reference.split()
    count = lambda n: len(normalize(" ".join(R[:n])).split())   # normalized words in the first n raw words

    def first_raw_index(target):                        # smallest n with count(n) >= target (binary search)
        lo, hi = 0, len(R)
        while lo < hi:
            mid = (lo + hi) // 2
            if count(mid) >= target:
                hi = mid
            else:
                lo = mid + 1
        return lo
    i0 = first_raw_index(info["ref_cut_start"])
    i1 = first_raw_index(info["ref_cut_start"] + info["ref_used"])
    return " ".join(R[max(0, i0 - margin): i1 + margin])


# ---------------- broken-output guard ----------------
def looks_broken(text: str, seconds: float, max_wps: float = 3.5, max_repeat: float = 0.08) -> str:
    """Why a transcript looks broken ('' if it looks fine).

    - too many words for the audio length (people speak about 1-3 words per second)
    - the model looped: many 8-word sequences appear more than once
    """
    w = normalize(text).split()
    if not w:
        return "empty"
    if seconds and len(w) / seconds > max_wps:
        return f"too long: {len(w)} words for {seconds/60:.1f} min"
    grams = [tuple(w[i:i + 8]) for i in range(max(0, len(w) - 8))]
    if grams:
        repeat = 1 - len(set(grams)) / len(grams)
        if repeat > max_repeat:
            return f"looped: {repeat:.0%} of the text repeats"
    return ""

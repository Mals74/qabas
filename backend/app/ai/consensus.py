"""Two-pass transcription: compare two readings, re-listen where they disagree, mark what stays unsure.

Provider-agnostic: the provider supplies three functions (pass A, pass B, re-listen) and this
module does the rest with plain Python, so it can be tested without any API.

  pass A (plain prompt)  ─┐
                          ├─ align word by word ─> disagreements ─> re-listen to short clips ─> patched text
  pass B (with context) ──┘                                               └─> still unsure ─> marked «غير مؤكد»

What is NOT treated as a disagreement (it doesn't change the meaning):
- a different و / ف prefix, spelling differences that normalize the same
- a repeated word (the sheikh's own repetition kept by one pass only)
- anything inside a recited verse that matched the Mushaf (the verified text is shown anyway)
- audience segments (never stored)
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from rapidfuzz.distance import Levenshtein

from ..arabic import normalize

# Negation / exception words: a difference involving one of these can flip the meaning
NEGATIONS = {"لا", "لم", "لن", "ما", "ليس", "ليست", "ليسوا", "لست", "لسنا", "لستم",
             "غير", "الا", "بلا", "دون", "كلا", "لولا"}
FILLERS = {"ا", "اا", "ام", "اه", "اي", "ايه", "امم"}
MAX_SPOTS_PER_MIN = 6     # more disagreements per minute than this: one pass is unreliable
CLUSTER_GAP = 60          # spots closer than this (seconds) share one re-listen clip
CLIP_PAD = 20             # seconds of audio before/after the spots in a clip
_PUNCT = ".,،؛:!?؟»«\"'()[]"


# ---------------------------------------------------------------- tokens

@dataclass
class Tok:
    seg: int              # index of the segment in its pass
    orig: str             # word as written (with punctuation)
    norm: str             # normalized form used for comparison
    cs: int               # char start inside the segment text
    ce: int               # char end
    time: float           # estimated time of the word (seconds)


def tokenize(segments: list[dict]) -> list[Tok]:
    """Words of a pass in order, with char offsets and an estimated time (interpolated in the segment)."""
    out = []
    for i, s in enumerate(segments):
        text = s.get("text") or ""
        words = list(re.finditer(r"\S+", text))
        start, end = float(s.get("start") or 0), float(s.get("end") or 0)
        end = max(end, start)
        for k, m in enumerate(words):
            norm = normalize(m.group()).replace(" ", "")
            if not norm:
                continue                       # punctuation on its own
            t = start + (end - start) * k / max(len(words), 1)
            out.append(Tok(i, m.group(), norm, m.start(), m.end(), t))
    return out


def is_negation(w: str) -> bool:
    return w in NEGATIONS or (len(w) > 2 and w[0] in "وف" and w[1:] in NEGATIONS)


def _strip_prefix(w: str) -> str:
    return w[1:] if len(w) > 2 and w[0] in "وف" else w


def _is_fragment(orig: str) -> bool:
    """A word the speaker cut off, written with a trailing dash or ellipsis."""
    return orig.rstrip("،,.؛:!؟?»") .endswith(("-", "ـ", "—", "…", "..."))


def _same_spelling(a: list[str], b: list[str]) -> bool:
    join = lambda ws: re.sub(r"(?<!\S)(و?)ان لا(?!\S)", r"\1الا", " ".join(_strip_prefix(w) for w in ws))
    return join(a) == join(b)


# ---------------------------------------------------------------- disagreements

@dataclass
class Spot:
    id: int
    seg: int                          # segment (in pass A) that holds the spot
    cs: int                           # char range in that segment's text (cs == ce: insertion point)
    ce: int
    a_text: str                       # what pass A wrote there ('' = nothing)
    b_text: str                       # what pass B wrote there
    before: str
    after: str
    time: float
    negation: bool
    verdict: dict = field(default_factory=dict)


def find_spots(seg_a: list[dict], seg_b: list[dict], skip_seg: Optional[Callable[[dict], bool]] = None,
               ctx: int = 8) -> tuple[list[Spot], int]:
    """Meaningful disagreements between pass A and pass B, located in pass A's segments.

    Returns (spots, crossing) where crossing counts differences that span two segments (ignored).
    """
    A, B = tokenize(seg_a), tokenize(seg_b)
    ops = [o for o in Levenshtein.opcodes([t.norm for t in A], [t.norm for t in B])]
    groups, cur = [], None                       # merge back-to-back non-equal blocks
    for o in ops:
        if o.tag == "equal":
            if cur:
                groups.append(cur); cur = None
            continue
        cur = [o.src_start, o.src_end, o.dest_start, o.dest_end] if cur is None else \
            [cur[0], o.src_end, cur[2], o.dest_end]
    if cur:
        groups.append(cur)

    spots, crossing = [], 0
    for a0, a1, b0, b1 in groups:
        # a word cut off mid-way ("المنفص-") is a false start one pass wrote down: not a disagreement
        if any(A[a0:a1]) and all(_is_fragment(t.orig) for t in A[a0:a1]) or \
           any(B[b0:b1]) and all(_is_fragment(t.orig) for t in B[b0:b1]):
            continue
        a_words = [t.norm for t in A[a0:a1] if not _is_fragment(t.orig)]
        b_words = [t.norm for t in B[b0:b1] if not _is_fragment(t.orig)]
        if "".join(a_words) == "".join(b_words):
            continue                                  # only spacing differs (ب لفظ / بلفظ)
        if [_strip_prefix(w) for w in a_words] == [_strip_prefix(w) for w in b_words]:
            continue                                  # only و / ف differs
        if _same_spelling(a_words, b_words):
            continue                                  # أن لا / ألا: same words, two spellings
        if not [w for w in a_words + b_words if w not in FILLERS]:
            continue                                  # fillers only
        extra = a_words or b_words
        if not extra:
            continue
        if not (a_words and b_words):                 # one side added words: a repetition?
            neighbours = {A[a0 - 1].norm if a0 > 0 else "", A[a1].norm if a1 < len(A) else ""}
            if all(w in neighbours for w in extra):
                continue
        # where the spot sits in pass A
        if a1 > a0:
            first, last = A[a0], A[a1 - 1]
            if first.seg != last.seg:
                crossing += 1
                continue
            seg, cs, ce, time = first.seg, first.cs, last.ce, first.time
        elif a0 > 0:                                  # insertion: right after the previous word of pass A
            anchor = A[a0 - 1]
            seg, cs, ce, time = anchor.seg, anchor.ce, anchor.ce, anchor.time
        elif A:                                       # insertion at the very beginning
            anchor = A[0]
            seg, cs, ce, time = anchor.seg, anchor.cs, anchor.cs, anchor.time
        else:
            continue
        if skip_seg and skip_seg(seg_a[seg]):
            continue
        spots.append(Spot(
            id=len(spots) + 1, seg=seg, cs=cs, ce=ce,
            a_text=" ".join(t.orig for t in A[a0:a1]), b_text=" ".join(t.orig for t in B[b0:b1]),
            before=" ".join(t.orig for t in A[max(0, a0 - ctx):a0]), after=" ".join(t.orig for t in A[a1:a1 + ctx]),
            time=time, negation=any(is_negation(w) for w in a_words + b_words)))
    return spots, crossing


# ---------------------------------------------------------------- re-listen clips

def clusters(spots: list[Spot], lo: float, hi: float, max_calls: int) -> list[tuple[float, float, list[Spot]]]:
    """Group spots into short clips (start, end, spots); never more than max_calls clips."""
    groups: list[list[Spot]] = []
    for s in sorted(spots, key=lambda s: s.time):
        if groups and s.time - groups[-1][-1].time <= CLUSTER_GAP:
            groups[-1].append(s)
        else:
            groups.append([s])
    while len(groups) > max(1, max_calls):          # merge the two closest neighbours
        gaps = [groups[i + 1][0].time - groups[i][-1].time for i in range(len(groups) - 1)]
        i = gaps.index(min(gaps))
        groups[i:i + 2] = [groups[i] + groups[i + 1]]
    return [(max(lo, g[0].time - CLIP_PAD), min(hi, g[-1].time + CLIP_PAD), g) for g in groups]


RELISTEN_PROMPT = """استمع إلى هذا المقطع من الدرس. اختلفت نسختان من التفريغ في المواضع التالية.
لكل موضع: توقيته التقريبي من بداية هذا المقطع، والكلام قبله، ثم ما كتبته النسخة A وما كتبته النسخة B، ثم الكلام بعده.

{items}

لكل موضع حدّد ما قاله المتكلم فعلًا:
- "A" إذا طابقت النسخة A ما قيل.
- "B" إذا طابقت النسخة B ما قيل.
- "other" إذا لم تطابق أيّ منهما، واكتب في heard الكلمات التي قيلت مكان الموضع فقط (لا تكتب ما قبله أو ما بعده).
- "unsure" إذا لم يكن الصوت واضحًا بما يكفي للجزم.
انتبه خاصة لأدوات النفي (لا، لم، لن، ما، ليس، غير، إلا): وجودها أو غيابها يقلب المعنى.
أعد لكل موضع: id و choice و heard."""


def relisten_prompt(spots: list[Spot], clip_start: float) -> str:
    def mmss(t):
        t = max(0, int(t - clip_start))
        return f"{t // 60}:{t % 60:02d}"
    items = "\n".join(
        f'{s.id}) [~{mmss(s.time)}] ...{s.before} [A: {s.a_text or "(لا شيء)"}] [B: {s.b_text or "(لا شيء)"}] {s.after}...'
        for s in spots)
    return RELISTEN_PROMPT.format(items=items)


def clean_verdict(spot: Spot, v: dict) -> dict:
    """Reject answers that can't be right: an 'other' much longer than the disputed words copied context."""
    choice = (v or {}).get("choice", "unsure")
    heard = ((v or {}).get("heard") or "").strip()
    if choice not in ("A", "B", "other", "unsure"):
        choice = "unsure"
    if choice == "other":
        n = max(len(spot.a_text.split()), len(spot.b_text.split()))
        if not heard or len(heard.split()) > n + 3:
            choice = "unsure"
    return {"choice": choice, "heard": heard}


# ---------------------------------------------------------------- apply

def apply(seg_a: list[dict], spots: list[Spot]) -> tuple[list[dict], dict]:
    """Patch pass A with the verdicts; unresolved spots become «غير مؤكد» marks on the segment.

    Each segment gets "uncertain": [{id, start, end, options, time, negation}] with char offsets
    into its final text (start == end means a word may be missing at that point).
    """
    out = [dict(s) for s in seg_a]
    for s in out:
        s.setdefault("uncertain", [])
    stats = {"disagreements": len(spots), "resolved": 0, "uncertain": 0}
    by_seg: dict[int, list[Spot]] = {}
    for sp in spots:
        by_seg.setdefault(sp.seg, []).append(sp)
    for seg_i, seg_spots in by_seg.items():
        text = out[seg_i]["text"]
        marks = []                                           # uncertain marks, offsets in the final text
        for sp in sorted(seg_spots, key=lambda s: s.cs, reverse=True):
            choice = sp.verdict.get("choice", "unsure")
            if choice in ("A", "B", "other"):
                new = {"A": sp.a_text, "B": sp.b_text, "other": sp.verdict.get("heard", "")}[choice]
                stats["resolved"] += 1
                mark = None
            else:
                new = sp.a_text                              # keep pass A, but mark it
                stats["uncertain"] += 1
                mark = {"options": [o for o in dict.fromkeys([sp.a_text, sp.b_text])],
                        "time": round(sp.time, 1), "negation": sp.negation}
            cs, ce = sp.cs, sp.ce
            if cs == ce and new:                              # inserting words: keep spacing
                piece = new + " " if cs < len(text) and not text[cs:cs + 1].isspace() else " " + new
                if cs == 0:
                    piece = new + " "
            else:
                piece = new
            if cs != ce and not new:                          # deleting words: drop one adjacent space
                if ce < len(text) and text[ce:ce + 1] == " ":
                    ce += 1
                elif cs > 0 and text[cs - 1:cs] == " ":
                    cs -= 1
            text = text[:cs] + piece + text[ce:]
            delta = len(piece) - (ce - cs)
            for m in marks:                                   # marks found earlier sit after this edit
                m["start"] += delta
                m["end"] += delta
            if mark is not None:
                word_start = cs + (len(piece) - len(piece.lstrip()))
                word_end = word_start + len(new)
                while word_end > word_start and text[word_end - 1] in _PUNCT:   # highlight the words, not the full stop
                    word_end -= 1
                mark.update(start=word_start, end=word_end,
                            options=list(dict.fromkeys(o.rstrip(_PUNCT) for o in mark["options"])))
                marks.append(mark)
        out[seg_i]["text"] = text
        out[seg_i]["uncertain"] = sorted(marks, key=lambda m: m["start"])
    for s in out:
        for n, m in enumerate(s["uncertain"], 1):
            m["id"] = n
    return out, stats


# ---------------------------------------------------------------- broken output guard

def looks_broken(segments: list[dict], seconds: float, max_wps: float = 3.5, max_repeat: float = 0.08) -> str:
    """Why a pass looks broken ('' if fine): far too many words for the audio, or the model looped."""
    words = normalize(" ".join(s.get("text") or "" for s in segments)).split()
    if not words:
        return "empty"
    if seconds > 30 and len(words) / seconds > max_wps:
        return f"too long: {len(words)} words for {seconds / 60:.1f} min"
    grams = [tuple(words[i:i + 8]) for i in range(max(0, len(words) - 8))]
    if len(grams) > 20:
        repeat = 1 - len(set(grams)) / len(grams)
        if repeat > max_repeat:
            return f"looped: {repeat:.0%} repeated"
    return ""


# ---------------------------------------------------------------- one window, start to finish

def run_window(pass_a: Callable[[float], list[dict]], pass_b: Callable[[float], list[dict]],
               relisten: Callable[[float, float, list], list[dict]], lo: float, hi: float,
               skip_seg: Optional[Callable[[dict], bool]] = None, max_calls: int = 4,
               on_progress: Optional[Callable[[str], None]] = None) -> tuple[list[dict], dict]:
    """Transcribe one window [lo, hi] twice, re-listen to the disagreements, return (segments, stats).

    pass_a(temperature) / pass_b(temperature) return segment dicts with absolute times;
    relisten(clip_start, clip_end, spots) returns [{id, choice, heard}]; build its prompt with relisten_prompt().
    """
    stats = {"passes": 2, "disagreements": 0, "resolved": 0, "uncertain": 0, "low_confidence": False, "notes": []}
    say = on_progress or (lambda m: None)

    def safe(pass_fn, name):
        segs = pass_fn(0)
        span = max([float(s.get("end") or s.get("start") or 0) for s in segs] + [lo]) - lo
        why = looks_broken(segs, span or (hi - lo))
        if why:
            stats["notes"].append(f"{name}: {why}, retried")
            segs = pass_fn(0.4)
            span = max([float(s.get("end") or s.get("start") or 0) for s in segs] + [lo]) - lo
            why = looks_broken(segs, span or (hi - lo))
        return segs, why

    a, a_bad = safe(pass_a, "A")
    b, b_bad = safe(pass_b, "B")
    if a_bad and not b_bad:                            # use the healthy pass as the base
        a, b, a_bad, b_bad = b, a, b_bad, a_bad
    if a_bad or b_bad or not a or not b:
        stats["low_confidence"] = bool(a_bad)
        stats["notes"].append("single pass only (the other was broken or empty)")
        out = [dict(s, uncertain=[], low_confidence=bool(a_bad)) for s in a]
        return out, stats

    spots, crossing = find_spots(a, b, skip_seg=skip_seg)
    max_spots = max(20, int(MAX_SPOTS_PER_MIN * (hi - lo) / 60))
    if len(spots) > max_spots:                          # the passes differ too much to trust either fully
        stats["low_confidence"] = True
        stats["notes"].append(f"{len(spots)} disagreements: marked as low confidence, only negations kept")
        spots = [s for s in spots if s.negation][:max_spots]
        for s in spots:
            s.verdict = {"choice": "unsure"}
    elif spots:
        say(f"مراجعة {len(spots)} موضعًا اختلفت فيه القراءتان بالاستماع مرة ثانية")
        for c0, c1, group in clusters(spots, lo, hi, max_calls):
            try:
                answers = {int(v.get("id", -1)): v for v in relisten(c0, c1, group) or []}
            except Exception as e:                       # re-listen failed: keep A and mark the spots
                stats["notes"].append(f"re-listen {int(c0)}-{int(c1)}s failed ({len(group)} spots kept as «غير مؤكد»): {str(e)[:80]}")
                answers = {}
            for s in group:
                s.verdict = clean_verdict(s, answers.get(s.id, {}))
    out, st = apply(a, spots)
    stats.update(disagreements=st["disagreements"], resolved=st["resolved"], uncertain=st["uncertain"])
    for s in out:
        s["low_confidence"] = stats["low_confidence"]
    return out, stats

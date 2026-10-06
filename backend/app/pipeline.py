"""The lesson pipeline and the grounded Q&A.

Principle: the AI proposes, the trusted source confirms.
  transcript (AI)  ->  Quran verses replaced by the verified Mushaf text
                   ->  hadith fragments sent for takhrij (on demand, Dorar)
                   ->  review cards kept only if their evidence exists in the sheikh's words
                   ->  answers kept only if their citations point to real passages
"""
import json
import traceback
from typing import Optional

from rapidfuzz import fuzz
from sqlmodel import Session, delete, select

from . import hadith, quran
from .ai import get_provider
from .ai.timeparse import fmt
from .arabic import normalize
from .config import CARD_EVIDENCE_THRESHOLD, HADITH_MAX_PER_LESSON
from .db import Book, Card, Lesson, Segment, engine

VALID_KINDS = {"matn", "sharh", "quran", "hadith", "audience", "other"}
# Shown instead of anything an attendee said (their voice/words are personal data)
AUDIENCE_PLACEHOLDER = "سؤال من أحد الحضور (لا يُفرَّغ حفاظًا على خصوصيته)"
# Kinds whose words are the sheikh's (or the matn he reads) and can support a card/answer
SHEIKH_KINDS = {"matn", "sharh", "hadith", "other"}


def _set(session: Session, lesson: Lesson, **fields) -> None:
    """Update lesson fields and commit immediately so the UI can poll progress."""
    for k, v in fields.items():
        setattr(lesson, k, v)
    session.add(lesson)
    session.commit()


def transcript_for_llm(segments: list[Segment]) -> str:
    """Compact transcript text for summary/cards prompts: "[seconds] (kind) text"."""
    lines = []
    for s in segments:
        if s.kind == "audience":
            continue
        lines.append(f"[{int(s.start)}] ({s.kind}) {s.text}")
    return "\n".join(lines)


def process_lesson(lesson_id: int, provider=None) -> None:
    """Run the full pipeline for one lesson. Called in a background thread."""
    provider = provider or get_provider()
    with Session(engine) as session:
        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            return
        try:
            _set(session, lesson, status="processing", error="", progress="بدء المعالجة")

            # 1) Transcribe (AI): two readings per window, disagreements re-listened (see ai/consensus.py)
            book = session.get(Book, lesson.book_id)
            raw = provider.transcribe(lesson, on_progress=lambda m: _set(session, lesson, progress=m),
                                      context={"book": book.title if book else ""})
            if not raw:
                raise RuntimeError("لم يُستخرج أي كلام من التسجيل")

            # 2) Clean, classify, verify Quran, link sharh to matn
            _set(session, lesson, progress="توثيق الآيات وربط الشرح بالمتن")
            session.exec(delete(Segment).where(Segment.lesson_id == lesson.id))
            session.exec(delete(Card).where(Card.lesson_id == lesson.id))
            segments = build_segments(lesson.id, raw)
            session.add_all(segments)
            stats = dict(getattr(provider, "last_stats", {}) or {})
            stats["uncertain"] = sum(len(json.loads(x.uncertain_json or "[]")) for x in segments)
            lesson.quality_json = json.dumps(stats, ensure_ascii=False)
            if segments:
                lesson.duration_sec = max(lesson.duration_sec or 0, segments[-1].end or segments[-1].start)
            session.commit()

            _finish(session, lesson, provider, segments)
        except Exception as e:
            message = str(e)
            if type(e).__name__ in ("QuotaError", "BusyError"):   # expected conditions: the message says it all
                print("stopped:", e)
                if type(e).__name__ == "BusyError" and lesson.source_type == "youtube":
                    # Google's reading of YouTube links fails on its own at times (500 INTERNAL); a file still works
                    message += (" وقد تكون قراءة روابط يوتيوب متوقفة مؤقتًا لدى Google: جرّب رفع الدرس ملفًا صوتيًا "
                                "من «تسجيل من الجهاز» في صفحة إضافة درس.")
            else:
                traceback.print_exc()
            _set(session, lesson, status="error", error=message[:500], progress="")


def _finish(session: Session, lesson: Lesson, provider, segments: list[Segment]) -> None:
    """Everything after the transcript: full hadith, summary, review cards.

    Each step is on its own: if one fails (busy servers, quota), the transcript and the other steps are kept, the lesson
    opens normally, and the failed step is recorded so the student can retry it with one button.
    """
    quality = json.loads(lesson.quality_json or "{}")
    for key in ("summary_failed", "cards_failed"):
        quality.pop(key, None)

    # 3) The full hadith for each hadith the sheikh quoted (nine hadith books)
    try:
        lookup_hadith(session, lesson, segments, provider)
    except Exception:
        traceback.print_exc()

    text = transcript_for_llm(segments)

    # 4) Summary (AI, labelled ملخص آلي in the UI)
    _set(session, lesson, progress="إعداد الملخص")
    try:
        lesson.summary_json = json.dumps(provider.summarize(text), ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        quality["summary_failed"] = str(e)[:200]

    # 5) Review cards, each checked against the sheikh's words
    _set(session, lesson, progress="استخراج بطاقات المراجعة")
    try:
        session.exec(delete(Card).where(Card.lesson_id == lesson.id))
        accepted, rejected = check_cards(lesson.id, provider.cards(text), segments)
        session.add_all(accepted)
        lesson.cards_rejected = rejected
    except Exception as e:
        traceback.print_exc()
        quality["cards_failed"] = str(e)[:200]

    lesson.quality_json = json.dumps(quality, ensure_ascii=False)
    _set(session, lesson, status="ready", progress="")


def previous_hadith(segments: list[Segment], seg: Segment, reach: int = 4) -> Optional[Segment]:
    """The hadith quoted just before this segment (at most `reach` segments earlier), if any."""
    before = [x for x in segments if x.kind == "hadith" and seg.idx - reach <= x.idx < seg.idx]
    return max(before, key=lambda x: x.idx) if before else None


def lookup_hadith(session: Session, lesson: Lesson, segments: list[Segment], provider) -> None:
    """Find the full hadith for the quotes that have no result yet, and keep the confirmed ones."""
    todo = [s for s in segments if s.kind == "hadith" and not s.hadith_json][:HADITH_MAX_PER_LESSON]
    if not todo:
        return
    _set(session, lesson, progress="البحث عن الأحاديث في كتب الحديث")
    results = {}
    normal = []
    for s in todo:                                           # «وفي رواية: بالنية» → a wording of the previous hadith
        prev = previous_hadith(segments, s) if hadith.needs_previous(s.hadith_query or s.text) else None
        r = hadith.takhrij_variant(prev.hadith_query or prev.text, s.hadith_query or s.text) if prev else None
        if r is not None and hadith.keep_variant(r, s.hadith_query or s.text):
            results[str(s.id)] = r
        else:
            normal.append(s)
    results.update(hadith.takhrij_many([(str(s.id), s.hadith_query or s.text) for s in normal], provider))
    for s in todo:
        r = results.get(str(s.id))
        if r and (r["results"] or r.get("variant_of")) and r["method"] != "candidate":   # unconfirmed candidates are not kept
            s.hadith_json = json.dumps(r, ensure_ascii=False)
            session.add(s)
    session.commit()


def retry_extras(lesson_id: int, provider=None) -> None:
    """Run the steps after the transcript again (summary, cards, hadith) without touching the transcript."""
    provider = provider or get_provider()
    with Session(engine) as session:
        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            return
        try:
            _set(session, lesson, status="processing", error="", progress="إعادة المحاولة")
            segments = session.exec(select(Segment).where(Segment.lesson_id == lesson.id).order_by(Segment.idx)).all()
            _finish(session, lesson, provider, segments)
        except Exception as e:
            traceback.print_exc()
            _set(session, lesson, status="ready", progress="")     # the transcript is still there


def build_segments(lesson_id: int, raw: list[dict]) -> list[Segment]:
    raw = sorted(raw, key=lambda r: float(r.get("start") or 0))
    out: list[Segment] = []
    last_matn = None
    for i, r in enumerate(raw):
        kind = (r.get("kind") or "sharh").strip().lower()
        kind = kind if kind in VALID_KINDS else "sharh"
        if kind == "matn" and hadith.is_variant_marker(r.get("text") or ""):
            kind = "sharh"                          # «وفي رواية:» is the sheikh introducing a wording, not the book
        text = (r.get("text") or "").strip()
        if not text:
            continue
        seg = Segment(lesson_id=lesson_id, idx=len(out), start=float(r.get("start") or 0),
                      end=float(r.get("end") or 0), kind=kind, text=text,
                      low_confidence=bool(r.get("low_confidence")),
                      uncertain_json=json.dumps(_valid_marks(r.get("uncertain"), text), ensure_ascii=False))
        if kind == "audience":
            seg.uncertain_json = "[]"
            seg.text = AUDIENCE_PLACEHOLDER          # never store what attendees said
            seg.source_label = "sheikh"
        elif kind == "quran":
            match = quran.verify(text)
            if match:
                seg.quran_json = match.to_json()
                # Verified -> we display the Mushaf text, not the transcription
                seg.source_label = "verified" if match.verified else "sheikh"
                if match.verified:
                    seg.uncertain_json = "[]"         # the Mushaf text is shown, so the transcription's doubts don't matter
        elif kind == "hadith":
            seg.hadith_query = text
        if kind == "matn":
            last_matn = seg.idx
        elif last_matn is not None and kind in ("sharh", "quran", "hadith"):
            seg.matn_idx = last_matn                  # this explanation belongs to that matn line
        out.append(seg)
    return out


def _valid_marks(marks, text: str) -> list[dict]:
    """Keep only well-formed «غير مؤكد» marks whose offsets fit the text."""
    good = []
    for m in marks or []:
        try:
            a, b = int(m["start"]), int(m["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= a <= b <= len(text):
            good.append({"id": len(good) + 1, "start": a, "end": b, "time": float(m.get("time") or 0),
                         "negation": bool(m.get("negation")),
                         "options": [str(o) for o in (m.get("options") or [])][:4]})
    return good


def resolve_mark(seg: Segment, mark_id: int, new_text: str) -> Segment:
    """The student settles an unsure spot: replace those words, shift the other marks, drop this mark."""
    marks = json.loads(seg.uncertain_json or "[]")
    mark = next((m for m in marks if m["id"] == mark_id), None)
    if mark is None:
        raise KeyError(mark_id)
    text, a, b = seg.text, mark["start"], mark["end"]
    new_text = (new_text or "").strip()
    if a == b and new_text:                           # a word was possibly missing here
        before = text[:a]
        piece = (" " if before and not before.endswith(" ") else "") + new_text + \
                (" " if text[a:a + 1] and not text[a:a + 1].isspace() else "")
    elif not new_text:                                # the student says nothing was said here
        piece = ""
        if b < len(text) and text[b:b + 1] == " ":
            b += 1
    else:
        piece = new_text
    seg.text = text[:a] + piece + text[b:]
    delta = len(piece) - (b - a)
    rest = []
    for m in marks:
        if m["id"] == mark_id:
            continue
        if m["start"] >= b:
            m["start"] += delta
            m["end"] += delta
        rest.append(m)
    seg.uncertain_json = json.dumps(rest, ensure_ascii=False)
    seg.corrected = True
    return seg


def check_cards(lesson_id: int, proposed: list[dict], segments: list[Segment]) -> tuple[list[Card], int]:
    """Keep a card only if its evidence quote really exists in the sheikh's words."""
    sheikh_text = normalize(" ".join(s.text for s in segments if s.kind in SHEIKH_KINDS))
    accepted, rejected = [], 0
    for c in proposed:
        quote = (c.get("evidence_quote") or "").strip()
        nq = normalize(quote)
        score = fuzz.partial_ratio(nq, sheikh_text) if len(nq.split()) >= 4 else 0
        if score < CARD_EVIDENCE_THRESHOLD or not c.get("question") or not c.get("answer"):
            rejected += 1
            continue
        kind = c.get("kind") if c.get("kind") in ("masalah", "mustalah", "dalil") else "masalah"
        start = _locate(quote, segments, fallback=float(c.get("evidence_start") or 0))
        accepted.append(Card(lesson_id=lesson_id, kind=kind, question=c["question"].strip(),
                             answer=c["answer"].strip(), evidence_quote=quote,
                             evidence_start=start, evidence_score=round(score, 1)))
    return accepted, rejected


def _locate(quote: str, segments: list[Segment], fallback: float) -> float:
    """Timestamp of the segment that actually contains the quote."""
    nq = normalize(quote)
    best, best_score = fallback, 0
    for s in segments:
        if s.kind not in SHEIKH_KINDS:
            continue
        sc = fuzz.partial_ratio(nq, normalize(s.text))
        if sc > best_score:
            best, best_score = s.start, sc
    return best


# ---------------- Ask the lessons (long context) ----------------

PERSONAL_NOTE = "هذا سؤال عن حالة شخصية؛ قَبَس لا يُفتي. هذه معلومة عامة من كلام الشيخ، ويُرجع في الحالة الخاصة إلى أهل العلم."
NOT_FOUND = "لم أجد جواب هذا السؤال في الدروس المسجلة."


def ask_book(session: Session, book_id: int, question: str, owner: str = "") -> dict:
    lessons = session.exec(select(Lesson).where(Lesson.book_id == book_id, Lesson.status == "ready",
                                                Lesson.owner.in_(["", owner]))
                           .order_by(Lesson.number)).all()
    if not lessons:
        return {"found": False, "answer": "لا توجد دروس جاهزة في هذا الكتاب بعد.", "citations": []}

    # Whole-book context: every lesson's full transcript (no chunking/embeddings)
    by_number, blocks, lesson_by_number = {}, [], {}
    for les in lessons:
        segs = session.exec(select(Segment).where(Segment.lesson_id == les.id).order_by(Segment.idx)).all()
        by_number[les.number] = [{"start": s.start, "kind": s.kind, "text": s.text} for s in segs]
        lesson_by_number[les.number] = (les, segs)
        body = "\n".join(f"[{int(s.start)}] {s.text}" for s in segs if s.kind != "audience")
        blocks.append(f"=== الدرس {les.number}: {les.title} ===\n{body}")
    context = "\n\n".join(blocks)

    result = get_provider().ask(question, context, by_number)

    # Verify every citation points to a real passage; drop the ones that don't
    citations = []
    for c in result.get("citations") or []:
        entry = lesson_by_number.get(int(c.get("lesson_number") or 0))
        if not entry:
            continue
        les, segs = entry
        seg = _nearest_supported(segs, float(c.get("start") or 0), c.get("quote") or "")
        if seg:
            citations.append({"lesson_id": les.id, "lesson_number": les.number, "lesson_title": les.title,
                              "start": seg.start, "time": fmt(seg.start), "quote": seg.text})

    found = bool(result.get("found")) and bool(citations)
    answer = (result.get("answer") or "").strip() if found else NOT_FOUND
    if found and result.get("personal"):
        answer = PERSONAL_NOTE + "\n\n" + answer
    return {"found": found, "answer": answer, "citations": citations, "label": "ai"}


def _nearest_supported(segs: list[Segment], start: float, quote: str):
    """A segment near the cited time whose text contains the quoted words."""
    nq = normalize(quote)
    candidates = [s for s in segs if s.kind in SHEIKH_KINDS and abs(s.start - start) <= 90] or \
                 [s for s in segs if s.kind in SHEIKH_KINDS]
    best, best_score = None, 0
    for s in candidates:
        sc = fuzz.partial_ratio(nq, normalize(s.text)) if nq else 0
        if sc > best_score:
            best, best_score = s, sc
    return best if best_score >= 80 else None


# ---------------- Search ----------------

def search(session: Session, q: str, limit: int = 30, owner: str = "") -> dict:
    nq = normalize(q)
    if len(nq) < 2:
        return {"books": [], "segments": []}
    books = [b for b in session.exec(select(Book).where(Book.owner.in_(["", owner]))).all() if nq in normalize(b.title)]
    hits = []
    rows = session.exec(select(Segment, Lesson, Book).where(Segment.lesson_id == Lesson.id)
                        .where(Lesson.book_id == Book.id).where(Lesson.owner.in_(["", owner]))).all()
    for seg, les, book in rows:
        if seg.kind == "audience":
            continue
        text = normalize(seg.text)
        if nq in text or (len(nq) > 6 and fuzz.partial_ratio(nq, text) >= 88):
            hits.append({"segment_id": seg.id, "lesson_id": les.id, "lesson_title": les.title,
                         "book_title": book.title, "start": seg.start, "time": fmt(seg.start),
                         "kind": seg.kind, "text": seg.text})
    return {"books": [{"id": b.id, "title": b.title} for b in books], "segments": hits[:limit]}

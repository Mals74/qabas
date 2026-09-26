"""The lesson pipeline and the grounded Q&A.

Principle: the AI proposes, the trusted source confirms.
  transcript (AI)  ->  Quran verses replaced by the verified Mushaf text
                   ->  hadith fragments sent for takhrij (on demand, Dorar)
                   ->  review cards kept only if their evidence exists in the sheikh's words
                   ->  answers kept only if their citations point to real passages
"""
import json
import traceback

from rapidfuzz import fuzz
from sqlmodel import Session, delete, select

from . import quran
from .ai import get_provider
from .ai.timeparse import fmt
from .arabic import normalize
from .config import CARD_EVIDENCE_THRESHOLD
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

            # 1) Transcribe (AI)
            raw = provider.transcribe(lesson, on_progress=lambda m: _set(session, lesson, progress=m))
            if not raw:
                raise RuntimeError("لم يُستخرج أي كلام من التسجيل")

            # 2) Clean, classify, verify Quran, link sharh to matn
            _set(session, lesson, progress="توثيق الآيات وربط الشرح بالمتن")
            session.exec(delete(Segment).where(Segment.lesson_id == lesson.id))
            session.exec(delete(Card).where(Card.lesson_id == lesson.id))
            segments = build_segments(lesson.id, raw)
            session.add_all(segments)
            if segments:
                lesson.duration_sec = max(lesson.duration_sec or 0, segments[-1].end or segments[-1].start)
            session.commit()

            text = transcript_for_llm(segments)

            # 3) Summary (AI, labelled ملخص آلي in the UI)
            _set(session, lesson, progress="إعداد الملخص")
            summary = provider.summarize(text)
            lesson.summary_json = json.dumps(summary, ensure_ascii=False)

            # 4) Review cards, each checked against the sheikh's words
            _set(session, lesson, progress="استخراج بطاقات المراجعة")
            accepted, rejected = check_cards(lesson.id, provider.cards(text), segments)
            session.add_all(accepted)
            _set(session, lesson, cards_rejected=rejected, status="ready", progress="")
        except Exception as e:
            traceback.print_exc()
            _set(session, lesson, status="error", error=str(e)[:500], progress="")


def build_segments(lesson_id: int, raw: list[dict]) -> list[Segment]:
    raw = sorted(raw, key=lambda r: float(r.get("start") or 0))
    out: list[Segment] = []
    last_matn = None
    for i, r in enumerate(raw):
        kind = (r.get("kind") or "sharh").strip().lower()
        kind = kind if kind in VALID_KINDS else "sharh"
        text = (r.get("text") or "").strip()
        if not text:
            continue
        seg = Segment(lesson_id=lesson_id, idx=len(out), start=float(r.get("start") or 0),
                      end=float(r.get("end") or 0), kind=kind, text=text)
        if kind == "audience":
            seg.text = AUDIENCE_PLACEHOLDER          # never store what attendees said
            seg.source_label = "sheikh"
        elif kind == "quran":
            match = quran.verify(text)
            if match:
                seg.quran_json = match.to_json()
                # Verified -> we display the Mushaf text, not the transcription
                seg.source_label = "verified" if match.verified else "sheikh"
        elif kind == "hadith":
            seg.hadith_query = text
        if kind == "matn":
            last_matn = seg.idx
        elif last_matn is not None and kind in ("sharh", "quran", "hadith"):
            seg.matn_idx = last_matn                  # this explanation belongs to that matn line
        out.append(seg)
    return out


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


def ask_book(session: Session, book_id: int, question: str) -> dict:
    lessons = session.exec(select(Lesson).where(Lesson.book_id == book_id, Lesson.status == "ready")
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

def search(session: Session, q: str, limit: int = 30) -> dict:
    nq = normalize(q)
    if len(nq) < 2:
        return {"books": [], "segments": []}
    books = [b for b in session.exec(select(Book)).all() if nq in normalize(b.title)]
    hits = []
    rows = session.exec(select(Segment, Lesson, Book).where(Segment.lesson_id == Lesson.id)
                        .where(Lesson.book_id == Book.id)).all()
    for seg, les, book in rows:
        if seg.kind == "audience":
            continue
        text = normalize(seg.text)
        if nq in text or (len(nq) > 6 and fuzz.partial_ratio(nq, text) >= 88):
            hits.append({"segment_id": seg.id, "lesson_id": les.id, "lesson_title": les.title,
                         "book_title": book.title, "start": seg.start, "time": fmt(seg.start),
                         "kind": seg.kind, "text": seg.text})
    return {"books": [{"id": b.id, "title": b.title} for b in books], "segments": hits[:limit]}

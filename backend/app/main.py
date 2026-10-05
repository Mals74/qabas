"""Qabas API (FastAPI). Also serves the built React app from frontend/dist.

Run locally:  uvicorn app.main:app --reload --port 8000   (from the backend folder)
"""
import json
from datetime import datetime, timezone
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session, func, select

from . import fahras, hadith, pipeline, quran, seed, youtube
from .ai import get_provider
from .ai.timeparse import fmt
from .ai import limits
from .config import (AI_PROVIDER, BASE_DIR, GEMINI_MODEL, HEAVY_DAILY_LIMIT, LIGHT_MODEL, MAX_LESSON_MINUTES,
                     SHOW_SAMPLE, UPLOAD_DIR)
from .db import Book, Card, Lesson, Note, Segment, engine, get_session, init_db

app = FastAPI(title="Qabas API")

ALLOWED_UPLOADS = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".mp4", ".webm", ".mov"}
KIND_LABELS = {"masalah": "المسائل", "mustalah": "المصطلحات", "dalil": "الأدلة"}


# ---------------- startup: tables + sample data ----------------

@app.on_event("startup")
def startup() -> None:
    init_db()
    with Session(engine) as s:
        fresh = s.exec(select(func.count()).select_from(Book)).one() == 0
        seed.import_seeds(s)                              # real lessons shipped in the repo (data/seed)
        # A restart kills any lesson being processed: say so instead of leaving it "processing" forever
        for les in s.exec(select(Lesson).where(Lesson.status.in_(["pending", "processing"]))).all():
            les.status, les.progress = "error", ""
            les.error = "انقطعت المعالجة لأن الخادم أُعيد تشغيله. احذف الدرس وأضفه مرة أخرى."
            s.add(les)
        s.commit()
        if fresh and SHOW_SAMPLE:                         # the labelled demo lesson (turn off with SHOW_SAMPLE=0)
            _seed_sample(s)
    threading.Thread(target=_warm_up, daemon=True).start()


def _warm_up() -> None:
    """Build the Quran and hadith search indexes once, while the server is idle, not in the middle of a lesson."""
    try:
        from . import hadith_index
        quran._index()
        fahras._roots()                                  # also unpacks the dictionaries on first start
        hadith_index.get_index()
        print("[startup] Quran and hadith indexes ready", flush=True)
    except Exception as e:                                   # the lesson pipeline builds them later if this fails
        print(f"[startup] warm-up skipped: {e}", flush=True)


def _seed_sample(s: Session) -> None:
    """Create the demo book + lesson and run it through the real pipeline (mock transcript)."""
    from .ai.mock import MockProvider
    from .ai.sample_data import SAMPLE_BOOK, SAMPLE_LESSON
    book = Book(**SAMPLE_BOOK)
    s.add(book)
    s.commit()
    lesson = Lesson(book_id=book.id, source_type="sample", is_sample=True, **SAMPLE_LESSON)
    s.add(lesson)
    s.commit()
    pipeline.process_lesson(lesson.id, provider=MockProvider())


def _run_in_background(lesson_id: int) -> None:
    threading.Thread(target=pipeline.process_lesson, args=(lesson_id,), daemon=True).start()


# ---------------- serializers ----------------

def lesson_card(les: Lesson, book: Optional[Book] = None) -> dict:
    return {
        "id": les.id, "book_id": les.book_id, "book_title": book.title if book else None,
        "number": les.number, "title": les.title, "sheikh": les.sheikh, "date": les.date,
        "duration": fmt(les.duration_sec), "status": les.status, "progress": les.progress,
        "error": les.error, "is_sample": les.is_sample, "source_type": les.source_type,
        **_eta(les),
    }


def _eta(les: Lesson) -> dict:
    """Rough time to finish, for the progress screen. Measured: a 10-minute clip took 3.2 minutes end to end
    (two readings, re-listening to disputed spots, verses, hadith, summary, cards) -> about 0.35 x audio + 1 minute."""
    if les.status not in ("pending", "processing"):
        return {}
    audio = les.duration_sec or (MAX_LESSON_MINUTES * 60 if MAX_LESSON_MINUTES else 3600)
    if MAX_LESSON_MINUTES:
        audio = min(audio, MAX_LESSON_MINUTES * 60)
    created = les.created_at if les.created_at.tzinfo else les.created_at.replace(tzinfo=timezone.utc)
    return {"elapsed_sec": int((datetime.now(timezone.utc) - created).total_seconds()),
            "expected_sec": int(audio * 0.35 + 60)}


def segment_out(seg: Segment) -> dict:
    d = {"id": seg.id, "idx": seg.idx, "start": seg.start, "time": fmt(seg.start), "kind": seg.kind,
         "text": seg.text, "matn_idx": seg.matn_idx, "source_label": seg.source_label,
         "uncertain": json.loads(seg.uncertain_json or "[]"), "low_confidence": seg.low_confidence,
         "corrected": seg.corrected}
    if seg.quran_json:
        q = json.loads(seg.quran_json)
        ayah = f"{q['ayah_from']}" if q["ayah_from"] == q["ayah_to"] else f"{q['ayah_from']}-{q['ayah_to']}"
        q["ref"] = f"[{q['surah_name']}: {ayah}]"
        q["text"] = quran.mushaf_text(q["surah"], q["ayah_from"], q["ayah_to"]) or q["text"]   # always the Mushaf's text
        q["source"] = quran.QURAN_SOURCE_LABEL
        for part in q.get("parts") or []:
            a = f"{part['ayah_from']}" if part["ayah_from"] == part["ayah_to"] else f"{part['ayah_from']}-{part['ayah_to']}"
            part["ref"] = f"[{part['surah_name']}: {a}]"
            part["text"] = quran.mushaf_text(part.get("surah") or part["surah_name"], part["ayah_from"],
                                             part["ayah_to"]) or part["text"]
        d["quran"] = q
    if seg.hadith_json:
        d["hadith"] = json.loads(seg.hadith_json)
    return d


def card_out(c: Card, les: Optional[Lesson] = None) -> dict:
    return {"id": c.id, "lesson_id": c.lesson_id, "kind": c.kind, "kind_label": KIND_LABELS.get(c.kind, ""),
            "question": c.question, "answer": c.answer, "evidence_quote": c.evidence_quote,
            "evidence_start": c.evidence_start, "time": fmt(c.evidence_start),
            "lesson_title": les.title if les else None}


# ---------------- status ----------------

@app.get("/api/status")
def status():
    live = AI_PROVIDER == "gemini"
    return {"provider": AI_PROVIDER, "model": GEMINI_MODEL if live else None,
            "light_model": LIGHT_MODEL if live else None,
            "max_minutes": MAX_LESSON_MINUTES,              # 0 = no cap
            "quota": limits.heavy.status() if live else None,
            "lessons_today": limits.lessons.status() if live else None}


# ---------------- books ----------------

class BookIn(BaseModel):
    title: str
    author: str = ""


@app.get("/api/books")
def list_books(s: Session = Depends(get_session)):
    out = []
    for b in s.exec(select(Book).order_by(Book.created_at.desc())).all():
        lessons = s.exec(select(Lesson).where(Lesson.book_id == b.id).order_by(Lesson.number)).all()
        out.append({"id": b.id, "title": b.title, "author": b.author, "lesson_count": len(lessons),
                    "last_lesson": lesson_card(lessons[-1]) if lessons else None})
    return out


@app.post("/api/books")
def create_book(body: BookIn, s: Session = Depends(get_session)):
    b = Book(title=body.title.strip(), author=body.author.strip())
    s.add(b)
    s.commit()
    s.refresh(b)
    return {"id": b.id, "title": b.title, "author": b.author}


@app.get("/api/books/{book_id}")
def get_book(book_id: int, s: Session = Depends(get_session)):
    b = s.get(Book, book_id) or _404("الكتاب غير موجود")
    lessons = s.exec(select(Lesson).where(Lesson.book_id == b.id).order_by(Lesson.number)).all()
    return {"id": b.id, "title": b.title, "author": b.author, "lessons": [lesson_card(l, b) for l in lessons]}


@app.get("/api/books/{book_id}/cards")
def book_cards(book_id: int, s: Session = Depends(get_session)):
    rows = s.exec(select(Card, Lesson).where(Card.lesson_id == Lesson.id, Lesson.book_id == book_id)
                  .order_by(Lesson.number, Card.evidence_start)).all()
    return [card_out(c, l) for c, l in rows]


class AskIn(BaseModel):
    question: str


@app.post("/api/books/{book_id}/ask")
def ask(book_id: int, body: AskIn, s: Session = Depends(get_session)):
    if not body.question.strip():
        raise HTTPException(400, "اكتب سؤالك")
    return pipeline.ask_book(s, book_id, body.question.strip())


# ---------------- lessons ----------------

@app.get("/api/lessons/recent")
def recent_lessons(s: Session = Depends(get_session)):
    rows = s.exec(select(Lesson, Book).where(Lesson.book_id == Book.id)
                  .order_by(Lesson.created_at.desc()).limit(10)).all()
    return [lesson_card(l, b) for l, b in rows]


@app.post("/api/lessons")
def create_lesson(
    title: str = Form(...),
    book_id: Optional[int] = Form(None),
    new_book_title: str = Form(""),
    sheikh: str = Form(""),
    date: str = Form(""),
    number: Optional[int] = Form(None),
    youtube_url: str = Form(""),
    file: Optional[UploadFile] = File(None),
    s: Session = Depends(get_session),
):
    # Budget: a daily cap on new lessons, checked before anything is saved
    if AI_PROVIDER == "gemini" and not limits.lessons.available():
        raise HTTPException(429, "بلغت النسخة التجريبية حدها اليومي من الدروس الجديدة (لأسباب تتعلق بالميزانية). "
                                 "تصفّح الدروس الجاهزة، أو جرّب غدًا بعد الساعة 10 صباحًا بتوقيت السعودية.")
    # Book: existing or new
    if not book_id:
        if not new_book_title.strip():
            raise HTTPException(400, "اختر كتابًا أو اكتب اسم كتاب جديد")
        book = Book(title=new_book_title.strip())
        s.add(book)
        s.commit()
        book_id = book.id
    elif not s.get(Book, book_id):
        raise HTTPException(404, "الكتاب غير موجود")

    if number is None:
        count = s.exec(select(func.count()).select_from(Lesson).where(Lesson.book_id == book_id)).one()
        number = count + 1

    lesson = Lesson(book_id=book_id, title=title.strip(), sheikh=sheikh.strip(), date=date.strip(), number=number)
    if youtube_url.strip():
        url = youtube.canonical(youtube_url)
        if not url:
            raise HTTPException(400, "رابط يوتيوب غير صحيح")
        lesson.source_type, lesson.source_url = "youtube", url
    elif file is not None and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_UPLOADS:
            raise HTTPException(400, "صيغة الملف غير مدعومة")
        dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        lesson.source_type, lesson.file_path = "file", str(dest)
    else:
        raise HTTPException(400, "أضف رابط يوتيوب أو ملف تسجيل")

    s.add(lesson)
    s.commit()
    s.refresh(lesson)
    if AI_PROVIDER == "gemini":
        limits.lessons.record()
    _run_in_background(lesson.id)
    return lesson_card(lesson)


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: int, s: Session = Depends(get_session)):
    les = s.get(Lesson, lesson_id) or _404("الدرس غير موجود")
    book = s.get(Book, les.book_id)
    segs = s.exec(select(Segment).where(Segment.lesson_id == les.id).order_by(Segment.idx)).all()
    notes = s.exec(select(Note).where(Note.lesson_id == les.id).order_by(Note.start)).all()
    cards = s.exec(select(Card).where(Card.lesson_id == les.id).order_by(Card.evidence_start)).all()
    return {
        **lesson_card(les, book),
        "source_url": les.source_url,
        "media_url": f"/api/lessons/{les.id}/media" if les.source_type == "file" else None,
        "media_kind": "video" if Path(les.file_path or "").suffix.lower() in (".mp4", ".webm", ".mov") else "audio",
        "youtube_id": _youtube_id(les.source_url),
        "mock_transcript": get_provider().name == "mock" and not les.is_sample,
        "segments": [segment_out(x) for x in segs],
        "summary": [{**p, "time": fmt(p.get("start", 0))} for p in json.loads(les.summary_json or "[]")],
        "notes": [{"id": n.id, "start": n.start, "time": fmt(n.start), "text": n.text} for n in notes],
        "cards": [card_out(c) for c in cards],
        "cards_rejected": les.cards_rejected,
        "quality": json.loads(les.quality_json or "{}"),
    }


@app.post("/api/lessons/{lesson_id}/reprocess")
def reprocess(lesson_id: int, s: Session = Depends(get_session)):
    les = s.get(Lesson, lesson_id) or _404("الدرس غير موجود")
    if les.is_sample:
        raise HTTPException(400, "الدرس التجريبي لا يعاد تفريغه")
    _run_in_background(les.id)
    return {"ok": True}


@app.post("/api/lessons/{lesson_id}/retry-extras")
def retry_extras(lesson_id: int, s: Session = Depends(get_session)):
    """Run the summary, the review cards and the hadith lookups again; the transcript is untouched."""
    les = s.get(Lesson, lesson_id) or _404("الدرس غير موجود")
    if les.status == "processing":
        raise HTTPException(409, "الدرس قيد المعالجة الآن")
    threading.Thread(target=pipeline.retry_extras, args=(les.id,), daemon=True).start()
    return {"ok": True}


@app.delete("/api/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, s: Session = Depends(get_session)):
    les = s.get(Lesson, lesson_id) or _404("الدرس غير موجود")
    for model in (Segment, Card, Note):
        for row in s.exec(select(model).where(model.lesson_id == les.id)).all():
            s.delete(row)
    if les.file_path:
        Path(les.file_path).unlink(missing_ok=True)
    s.delete(les)
    s.commit()
    return {"ok": True}


@app.get("/api/lessons/{lesson_id}/media")
def lesson_media(lesson_id: int, s: Session = Depends(get_session)):
    les = s.get(Lesson, lesson_id) or _404("الدرس غير موجود")
    if not les.file_path or not Path(les.file_path).exists():
        _404("لا يوجد ملف")
    return FileResponse(les.file_path)


# ---------------- notes ----------------

class NoteIn(BaseModel):
    start: float = 0
    text: str


@app.post("/api/lessons/{lesson_id}/notes")
def add_note(lesson_id: int, body: NoteIn, s: Session = Depends(get_session)):
    s.get(Lesson, lesson_id) or _404("الدرس غير موجود")
    n = Note(lesson_id=lesson_id, start=body.start, text=body.text.strip())
    s.add(n)
    s.commit()
    s.refresh(n)
    return {"id": n.id, "start": n.start, "time": fmt(n.start), "text": n.text}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: int, s: Session = Depends(get_session)):
    n = s.get(Note, note_id) or _404("الملاحظة غير موجودة")
    s.delete(n)
    s.commit()
    return {"ok": True}


# ---------------- hadith takhrij ----------------

@app.get("/api/segments/{segment_id}/takhrij")
def takhrij(segment_id: int, s: Session = Depends(get_session)):
    seg = s.get(Segment, segment_id) or _404("المقطع غير موجود")
    if seg.hadith_json:
        return json.loads(seg.hadith_json)
    result = hadith.takhrij(seg.hadith_query or seg.text, get_provider())
    if result["results"] and result.get("method") != "candidate":   # cache only confirmed answers
        seg.hadith_json = json.dumps(result, ensure_ascii=False)
        s.add(seg)
        s.commit()
    return result


# ---------------- «غير مؤكد» marks ----------------

class ResolveIn(BaseModel):
    mark_id: int
    text: str = ""


@app.post("/api/segments/{segment_id}/resolve")
def resolve(segment_id: int, body: ResolveIn, s: Session = Depends(get_session)):
    seg = s.get(Segment, segment_id) or _404("المقطع غير موجود")
    try:
        pipeline.resolve_mark(seg, body.mark_id, body.text)
    except KeyError:
        _404("هذا الموضع غير موجود أو حُسم من قبل")
    s.add(seg)
    s.commit()
    s.refresh(seg)
    return segment_out(seg)


# ---------------- search ----------------

# ---------------- الفهرس: word meanings from classical dictionaries (no AI) ----------------

@app.get("/api/fahras")
def fahras_lookup(word: str):
    if not fahras.available():
        raise HTTPException(503, "الفهرس غير متاح على هذا الخادم")
    if len(fahras.clean_word(word)) < 2:
        raise HTTPException(400, "اكتب كلمة من حرفين على الأقل")
    return fahras.lookup(word[:40])


@app.get("/api/fahras/root")
def fahras_root(root: str):
    """Full entries of one root (the lookup returns shortened ones)."""
    found = fahras.entries(root[:40])
    if not found:
        raise HTTPException(404, "لا يوجد هذا الجذر في المعاجم")
    return {"root": root.strip('"'), "source": fahras.SOURCE, "entries": found}


@app.get("/api/fahras/browse")
def fahras_browse(prefix: str):
    return {"roots": fahras.browse(prefix[:10])}


@app.get("/api/search")
def search(q: str = "", s: Session = Depends(get_session)):
    return pipeline.search(s, q)


# ---------------- helpers ----------------

def _404(msg: str):
    raise HTTPException(404, msg)


def _youtube_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/live/|/shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


# ---------------- frontend (built React app) ----------------

DIST = BASE_DIR.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        """Serve index.html for every non-API route (client-side routing)."""
        target = DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")

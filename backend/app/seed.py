"""Lessons processed once and shipped inside the repo, so the live app opens with real content.

Why: the free hosting forgets every file at each restart, and the free Gemini quota is small (and shared by everyone
who opens the link). A lesson processed once by the team is exported to `data/seed/<name>.json` and loaded from there
each time the app starts: no AI request is spent when a visitor opens it.

Commands (run from the backend folder, with GEMINI_API_KEY set):
    python -m app.seed process --url https://youtu.be/XXXXXXXXXXX --book "اسم الكتاب" --title "الدرس 1" \\
                               --sheikh "الشيخ ..." --minutes 10 --name lesson1
        runs the whole pipeline in a scratch database and writes data/seed/lesson1.json
    python -m app.seed export LESSON_ID NAME      exports a lesson already in the app's database
    python -m app.seed list                       shows what is in data/seed
"""
import os
import sys

if __name__ == "__main__":                        # a scratch database, so the app's own data is never touched
    os.environ.setdefault("DATABASE_URL", "sqlite:///seed_work.db")

import argparse
import json
from pathlib import Path

from sqlmodel import Session, select

from .config import SEED_DIR
from .db import Book, Card, Lesson, Segment, engine, init_db

_LESSON_FIELDS = ["number", "title", "sheikh", "date", "source_type", "source_url", "duration_sec", "cards_rejected",
                  "summary_json", "quality_json"]
_SEGMENT_FIELDS = ["idx", "start", "end", "kind", "text", "matn_idx", "source_label", "quran_json", "hadith_query",
                   "hadith_json", "uncertain_json", "low_confidence", "corrected"]
_CARD_FIELDS = ["kind", "question", "answer", "evidence_quote", "evidence_start", "evidence_score"]


def export_lesson(session: Session, lesson_id: int) -> dict:
    """Everything needed to recreate a finished lesson (never the student's private notes)."""
    les = session.get(Lesson, lesson_id)
    if not les or les.status != "ready":
        raise SystemExit(f"الدرس {lesson_id} غير جاهز أو غير موجود")
    book = session.get(Book, les.book_id)
    segs = session.exec(select(Segment).where(Segment.lesson_id == les.id).order_by(Segment.idx)).all()
    cards = session.exec(select(Card).where(Card.lesson_id == les.id).order_by(Card.evidence_start)).all()
    return {
        "book": {"title": book.title, "author": book.author},
        "lesson": {f: getattr(les, f) for f in _LESSON_FIELDS},
        "segments": [{f: getattr(x, f) for f in _SEGMENT_FIELDS} for x in segs],
        "cards": [{f: getattr(c, f) for f in _CARD_FIELDS} for c in cards],
    }


def write_seed(session: Session, lesson_id: int, name: str) -> Path:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    path = SEED_DIR / f"{name}.json"
    path.write_text(json.dumps(export_lesson(session, lesson_id), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def import_seeds(session: Session) -> int:
    """Create the lessons in data/seed that are not in the database yet. Returns how many were added."""
    added = 0
    for path in sorted(SEED_DIR.glob("*.json")) if SEED_DIR.exists() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            b, l = data["book"], data["lesson"]
        except (ValueError, KeyError):
            print(f"seed: skipped {path.name} (not a valid lesson file)")
            continue
        book = session.exec(select(Book).where(Book.title == b["title"], Book.owner == "")).first()
        if book is None:
            book = Book(title=b["title"], author=b.get("author", ""))
            session.add(book)
            session.commit()
            session.refresh(book)
        if session.exec(select(Lesson).where(Lesson.book_id == book.id, Lesson.number == l["number"],
                                             Lesson.title == l["title"], Lesson.owner == "")).first():
            continue                                     # already loaded
        lesson = Lesson(book_id=book.id, status="ready", is_sample=False, **l)
        session.add(lesson)
        session.commit()
        session.refresh(lesson)
        session.add_all([Segment(lesson_id=lesson.id, **x) for x in data.get("segments", [])])
        session.add_all([Card(lesson_id=lesson.id, **x) for x in data.get("cards", [])])
        session.commit()
        added += 1
    return added


def process(args) -> None:
    """Run the real pipeline on one recording and save the result as a seed file."""
    from . import pipeline, youtube
    if args.url:
        url = youtube.canonical(args.url)
        if not url:
            raise SystemExit(f"Not a YouTube video link: {args.url}")
        args.url = url
    init_db()
    with Session(engine) as s:
        book = Book(title=args.book, author=args.author)
        s.add(book)
        s.commit()
        s.refresh(book)
        lesson = Lesson(book_id=book.id, number=args.number, title=args.title, sheikh=args.sheikh, date=args.date,
                        source_type="youtube" if args.url else "file", source_url=args.url or "",
                        file_path=args.file or "", duration_sec=args.minutes * 60 if args.minutes else 0)
        s.add(lesson)
        s.commit()
        lesson_id = lesson.id
    pipeline.process_lesson(lesson_id)                   # synchronous; prints its own errors
    with Session(engine) as s:
        les = s.get(Lesson, lesson_id)
        print(f"status: {les.status} {les.error}")
        quality = json.loads(les.quality_json or "{}")
        print("quality:", json.dumps({k: v for k, v in quality.items() if k != "notes"}, ensure_ascii=False))
        for note in quality.get("notes", []):
            print("  note:", note)
        segs = s.exec(select(Segment).where(Segment.lesson_id == lesson_id)).all()
        kinds = {}
        for x in segs:
            kinds[x.kind] = kinds.get(x.kind, 0) + 1
        from .ai import limits
        print("main-model requests sent (failed ones included):", limits.heavy.status()["used"], "(paid Tier 1: 10,000 a day; free tier: 20)")
        print("segments:", kinds, "| hadith found:", sum(1 for x in segs if x.hadith_json),
              "| verified verses:", sum(1 for x in segs if x.quran_json and json.loads(x.quran_json).get("verified")))
        if les.status == "ready":
            print("written:", write_seed(s, lesson_id, args.name))
            return
        print("\nWHAT HAPPENED:", explain(les.error or ""))
        raise SystemExit(1)


def rehadith(only: str = "") -> None:
    """Look up the full hadith again for the lessons already in data/seed, without re-transcribing."""
    from . import hadith
    from .ai import get_provider
    provider = get_provider()
    for path in sorted(SEED_DIR.glob("*.json")):
        if only and path.stem != only:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        segs = [x for x in data["segments"] if x["kind"] == "hadith"]
        print(f"━━━━ {path.stem}: {len(segs)} hadith quotes")
        if not segs:
            continue
        results = hadith.takhrij_many([(str(x["idx"]), x.get("hadith_query") or x["text"]) for x in segs], provider)
        for x in segs:
            r = results[str(x["idx"])]
            keep = bool(r["results"]) and r["method"] in ("rule", "check")
            x["hadith_json"] = json.dumps(r, ensure_ascii=False) if keep else ""
            print(f"\n  الشيخ: «{x['text']}»")
            if r["results"]:
                h = r["results"][0]
                print(f"  → [{r['method']}] {h['source']} — {h.get('grade', '')}")
                print(f"    {h['text'][:200]}")
                if not keep:
                    print("    (not saved: unconfirmed)")
            else:
                print(f"  → [{r['method']}] {r['message']}")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def explain(error: str) -> str:
    """One plain sentence for the person running the notebook."""
    if "503" in error or "مزدحمة" in error or "متوقفة" in error or "UNAVAILABLE" in error:
        return ("Google's servers were overloaded (not your fault). Careful: Google counts failed attempts against the "
                "daily quota, so check the Rate limit page in AI Studio before running this cell again.")
    if "الحد اليومي" in error or "PerDay" in error:
        return "The free daily quota is used up. It resets at 10:00 Saudi time; run this cell again after that."
    if "429" in error:
        return "Too many requests in one minute. Wait a minute and run this cell again."
    if "API key" in error or "API_KEY" in error or "401" in error or "403" in error:
        return "Google rejected the API key. Check the GEMINI_API_KEY secret (and that Notebook access is on)."
    if "404" in error or "NOT_FOUND" in error:
        return "A model name or the video was not found. Check the link, or set MODEL to a name from section 2."
    if "400" in error or "INVALID_ARGUMENT" in error:
        return ("Google refused the video (it may be private, age-restricted, a live stream still running, or too long). "
                "Try another link, or copy the error above to Claude.")
    return "Unexpected error: copy the lines above to Claude."


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.seed")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("process")
    p.add_argument("--url", default="")
    p.add_argument("--file", default="")
    p.add_argument("--book", required=True)
    p.add_argument("--author", default="")
    p.add_argument("--title", required=True)
    p.add_argument("--sheikh", default="")
    p.add_argument("--date", default="")
    p.add_argument("--number", type=int, default=1)
    p.add_argument("--minutes", type=float, default=10)
    p.add_argument("--name", required=True)
    e = sub.add_parser("export")
    e.add_argument("lesson_id", type=int)
    e.add_argument("name")
    sub.add_parser("list")
    h = sub.add_parser("rehadith")
    h.add_argument("--name", default="")
    args = ap.parse_args()
    if args.cmd == "process":
        if not (args.url or args.file):
            sys.exit("أعطِ --url أو --file")
        process(args)
    elif args.cmd == "rehadith":
        rehadith(args.name)
    elif args.cmd == "export":
        with Session(engine) as s:
            print("written:", write_seed(s, args.lesson_id, args.name))
    else:
        for path in sorted(SEED_DIR.glob("*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            print(f"{path.name}: {d['book']['title']} | {d['lesson']['title']} | {len(d['segments'])} segments, {len(d['cards'])} cards")


if __name__ == "__main__":
    main()

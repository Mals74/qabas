"""Database models (SQLModel on top of SQLAlchemy).

Structure mirrors the product: a private notebook holds Books; each Book has
Lessons (one per session/date); each Lesson has timestamped Segments, review
Cards and the student's own Notes.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine

from .config import DATABASE_URL

# check_same_thread=False lets FastAPI's threads share the SQLite connection
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)


class Book(SQLModel, table=True):
    """A book being studied, e.g. كتاب التوحيد."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: str = ""                     # author of the matn
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Lesson(SQLModel, table=True):
    """One recorded session of a book."""
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="book.id", index=True)
    number: int = 1                      # lesson number within the book
    title: str
    sheikh: str = ""
    date: str = ""                       # free text so Hijri dates work (e.g. ١٢ رجب ١٤٤٦)
    source_type: str = "youtube"         # "youtube" or "file"
    source_url: str = ""                 # YouTube link (no download; passed to Gemini directly)
    file_path: str = ""                  # uploaded recording on disk
    duration_sec: float = 0
    status: str = "pending"              # pending | processing | ready | error
    error: str = ""
    progress: str = ""                   # human-readable step while processing
    cards_rejected: int = 0              # AI-proposed cards dropped for lack of evidence
    summary_json: str = "[]"             # AI summary points (labelled ملخص آلي)
    is_sample: bool = False              # sample/demo data, shown with a badge
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Segment(SQLModel, table=True):
    """A timestamped piece of the transcript."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    idx: int                             # order within the lesson
    start: float                         # seconds from the beginning of the recording
    end: float = 0
    kind: str = "sharh"                  # matn | sharh | quran | hadith | other
    text: str                            # verbatim words as spoken
    matn_idx: Optional[int] = None       # for sharh: index of the matn line it explains
    source_label: str = "sheikh"         # verified | sheikh | ai
    quran_json: str = ""                 # verified verse (see quran.py) when kind == quran
    hadith_query: str = ""               # the fragment the sheikh said, used for takhrij
    hadith_json: str = ""                # cached Dorar result (only cached when the lookup succeeded)


class Card(SQLModel, table=True):
    """A review card. Accepted only if its evidence quote exists in the sheikh's words."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    kind: str = "masalah"                # masalah (مسألة) | mustalah (مصطلح) | dalil (دليل)
    question: str
    answer: str
    evidence_quote: str                  # exact words from the transcript
    evidence_start: float = 0            # timestamp of the evidence
    evidence_score: float = 0            # fuzzy match score of the quote against the transcript


class Note(SQLModel, table=True):
    """The student's own note, pinned to a minute of the lesson."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    start: float = 0
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    """Create tables if they don't exist yet."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency that yields a DB session per request."""
    with Session(engine) as session:
        yield session

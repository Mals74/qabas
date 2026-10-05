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
IS_SQLITE = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if IS_SQLITE else {}
# Hosted Postgres (Neon) closes idle connections and sleeps: check each connection before use, renew them hourly
engine = create_engine(DATABASE_URL, connect_args=_connect_args,
                       **({} if IS_SQLITE else {"pool_pre_ping": True, "pool_recycle": 1800, "pool_size": 5}))


class Book(SQLModel, table=True):
    """A book being studied, e.g. كتاب التوحيد."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: str = ""                     # author of the matn
    owner: str = Field(default="", index=True)   # "" = the ready-made lessons everyone sees; else one device's id
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
    quality_json: str = "{}"             # two-pass stats: disagreements, resolved by re-listening, still unsure
    is_sample: bool = False              # sample/demo data, shown with a badge
    owner: str = Field(default="", index=True)   # "" = ready-made lesson shown to everyone; else only its owner
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
    uncertain_json: str = "[]"           # words the two readings disagreed on and re-listening couldn't settle
    low_confidence: bool = False         # the readings of this part differed too much (poor audio)
    corrected: bool = False              # the student fixed a word in this segment


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
    owner: str = Field(default="", index=True)   # notes are always private to the device that wrote them
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Columns added after the first release: added to existing databases at startup
_NEW_COLUMNS = {
    "book": {"owner": "VARCHAR DEFAULT ''"},
    "note": {"owner": "VARCHAR DEFAULT ''"},
    "lesson": {"quality_json": "VARCHAR DEFAULT '{}'", "owner": "VARCHAR DEFAULT ''"},
    "segment": {"uncertain_json": "VARCHAR DEFAULT '[]'", "low_confidence": "BOOLEAN DEFAULT FALSE",
                "corrected": "BOOLEAN DEFAULT FALSE"},
}


def init_db() -> None:
    """Create tables if they don't exist yet, and add any newer columns to older databases."""
    SQLModel.metadata.create_all(engine)
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _NEW_COLUMNS.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_session():
    """FastAPI dependency that yields a DB session per request."""
    with Session(engine) as session:
        yield session

"""Central settings for Qabas, read from environment variables.

On Replit, set these under "Secrets". Nothing here should ever be hard-coded
(especially the API key).
"""
import os
from pathlib import Path

# Folder that holds this backend (…/backend)
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Read KEY=value lines from .env (repo root or backend/) without overriding real environment variables."""
    for path in (BASE_DIR.parent / ".env", BASE_DIR / ".env"):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Where data files (Quran text, uploads, SQLite db) live
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# SQLite now; swap the URL for PostgreSQL later without code changes
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or f"sqlite:///{DATA_DIR / 'qabas.db'}"
# A hosted Postgres (e.g. Neon) gives postgres:// or postgresql:// links: use the psycopg 3 driver for them
for _p in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_p):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_p):]

# Gemini settings. If no key is set, the app runs on the mock AI provider.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Model names change over time; override with the GEMINI_MODEL secret if this one is retired
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Long lessons are transcribed in windows of this many minutes
CHUNK_MINUTES = int(os.getenv("CHUNK_MINUTES", "20"))
# Safety cap: never process more than this many windows (20 min x 9 = 3 hours)
MAX_CHUNKS = int(os.getenv("MAX_CHUNKS", "9"))
# Two readings per window (plain + with book/sheikh context); where they disagree, Gemini listens again.
# Set to 1 to save requests (e.g. on the free tier): single pass, no re-listening.
TRANSCRIBE_PASSES = int(os.getenv("TRANSCRIBE_PASSES", "2"))
# At most this many short re-listen requests per window (nearby disagreements share one clip)
RELISTEN_MAX_CALLS = int(os.getenv("RELISTEN_MAX_CALLS", "4"))

# Light tasks (summary, cards, questions, the hadith check) run on this cheaper model, which has its own quota,
# so the main model's scarce daily quota is spent on transcription only. It is also the backup for transcription.
LIGHT_MODEL = os.getenv("GEMINI_LIGHT_MODEL", "gemini-flash-lite-latest")
# When the main model is overloaded (503) or out of daily quota, transcription moves to other Flash models (each has
# its own free quota). Empty (the default) = found automatically: the newest other "gemini-X.Y-flash" models this key
# can use. Aliases like gemini-flash-latest are avoided: they point at the main model and share its quota.
# Flash-Lite is never a busy backup: in our tests it made 2-3x more transcription errors. Comma-separated.
BUSY_BACKUP_MODELS = [m.strip() for m in os.getenv("GEMINI_BUSY_BACKUPS", "").split(",")
                      if m.strip() and m.strip() != GEMINI_MODEL] or None
# Last resort when every Flash model is out of daily quota: transcribe with the light model (and say so)?
# The live app allows it (a result with a warning beats nothing); the demo-lesson notebook turns it off.
ALLOW_LIGHT_TRANSCRIPTION = os.getenv("ALLOW_LIGHT_TRANSCRIPTION", "1") == "1"
# After the main model was found overloaded, send transcription straight to the backup for this many seconds
BUSY_COOLDOWN_SEC = int(os.getenv("BUSY_COOLDOWN_SEC", "600"))
# Requests per day the app sends to the main model before switching to LIGHT_MODEL (paid Tier 1: 10,000; free: 20). 0 = no limit.
HEAVY_DAILY_LIMIT = int(os.getenv("HEAVY_DAILY_LIMIT", "200"))
# New lessons anyone can add per day on the live link (budget: the demo runs on a small prepaid credit). 0 = no limit.
MAX_LESSONS_PER_DAY = int(os.getenv("MAX_LESSONS_PER_DAY", "5"))
# Longest recording processed, in minutes (protects the free quota when strangers use the live link). 0 = no limit.
MAX_LESSON_MINUTES = float(os.getenv("MAX_LESSON_MINUTES", "10"))

# "mock" or "gemini". Defaults to gemini when a key exists.
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini" if GEMINI_API_KEY else "mock")

# Quran verification: minimum fuzzy score (0-100) to call a recited verse "verified"
QURAN_MATCH_THRESHOLD = float(os.getenv("QURAN_MATCH_THRESHOLD", "85"))
# Review cards: minimum score for the card's evidence quote to be found in the sheikh's words
CARD_EVIDENCE_THRESHOLD = float(os.getenv("CARD_EVIDENCE_THRESHOLD", "88"))

# Hadith search over nine hadith books (Haystack BM25 -> quote rule -> Flash-Lite check); Dorar link to verify
HADITH_CORPUS = DATA_DIR / "hadith_corpus.json.gz"
HADITH_CANDIDATES = int(os.getenv("HADITH_CANDIDATES", "12"))          # distinct hadith the check gets to see
HADITH_RULE_WORDS = int(os.getenv("HADITH_RULE_WORDS", "5"))           # consecutive words that settle a match
HADITH_PER_REQUEST = int(os.getenv("HADITH_PER_REQUEST", "4"))         # quotes per check request
HADITH_MAX_PER_LESSON = int(os.getenv("HADITH_MAX_PER_LESSON", "12"))  # quotes looked up automatically per lesson

# Lessons processed once and shipped inside the repo (loaded at startup; see app/seed.py)
SEED_DIR = Path(os.getenv("SEED_DIR", str(DATA_DIR / "seed")))
# The labelled demo lesson (invented text) is added to an empty database; set SHOW_SAMPLE=0 in the live app
SHOW_SAMPLE = os.getenv("SHOW_SAMPLE", "1") != "0"

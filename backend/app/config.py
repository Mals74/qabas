"""Central settings for Qabas, read from environment variables.

On Replit, set these under "Secrets". Nothing here should ever be hard-coded
(especially the API key).
"""
import os
from pathlib import Path

# Folder that holds this backend (…/backend)
BASE_DIR = Path(__file__).resolve().parent.parent

# Where data files (Quran text, uploads, SQLite db) live
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# SQLite now; swap the URL for PostgreSQL later without code changes
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'qabas.db'}")

# Gemini settings. If no key is set, the app runs on the mock AI provider.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Model names change over time; override with the GEMINI_MODEL secret if this one is retired
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Long lessons are transcribed in windows of this many minutes
CHUNK_MINUTES = int(os.getenv("CHUNK_MINUTES", "20"))
# Safety cap: never process more than this many windows (20 min x 9 = 3 hours)
MAX_CHUNKS = int(os.getenv("MAX_CHUNKS", "9"))

# "mock" or "gemini". Defaults to gemini when a key exists.
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini" if GEMINI_API_KEY else "mock")

# Quran verification: minimum fuzzy score (0-100) to call a recited verse "verified"
QURAN_MATCH_THRESHOLD = float(os.getenv("QURAN_MATCH_THRESHOLD", "85"))
# Review cards: minimum score for the card's evidence quote to be found in the sheikh's words
CARD_EVIDENCE_THRESHOLD = float(os.getenv("CARD_EVIDENCE_THRESHOLD", "88"))

# Dorar (الدرر السنية) public API endpoint
DORAR_API_URL = os.getenv("DORAR_API_URL", "https://dorar.net/dorar_api.json")
DORAR_TIMEOUT = float(os.getenv("DORAR_TIMEOUT", "12"))

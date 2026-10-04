"""YouTube links: one canonical form, so Gemini always gets the link shape it documents."""
import re
from typing import Optional

_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/embed/|/live/|/shorts/)([A-Za-z0-9_-]{11})")
_HOST = re.compile(r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/", re.I)


def video_id(url: str) -> Optional[str]:
    m = _ID.search(url or "")
    return m.group(1) if m else None


def canonical(url: str) -> Optional[str]:
    """https://www.youtube.com/watch?v=ID with tracking (?si=), start times and playlists removed; None if not YouTube."""
    url = (url or "").strip()
    if not _HOST.match(url):
        return None
    vid = video_id(url)
    return f"https://www.youtube.com/watch?v={vid}" if vid else None

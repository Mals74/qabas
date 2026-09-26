"""Parse timestamps that may come back as "HH:MM:SS", "MM:SS", "75.5" or a number."""
import re


def to_seconds(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    # Arabic-Indic digits -> Western
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    parts = [p for p in re.split(r"[:：]", text) if p != ""]
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return 0.0
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def fmt(seconds: float) -> str:
    """Seconds -> "M:SS" or "H:MM:SS" for display."""
    s = int(round(seconds or 0))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

"""Hadith takhrij through the Dorar (الدرر السنية) public API.

Rule (from the challenge's scientific standard): a hadith is never shown
without a source, and we never generate hadith text ourselves. If Dorar
cannot be reached, we return no text, only a search link, and say so.

API: GET https://dorar.net/dorar_api.json?skey=<words>
Returns JSON whose `ahadith.result` is an HTML fragment with pairs of
  <div class="hadith">…text…</div>
  <div class="hadith-info"><span class="info-subtitle">الراوي:</span> … </div>
"""
import re
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from .arabic import strip_diacritics
from .config import DORAR_API_URL, DORAR_TIMEOUT

# Labels Dorar uses inside hadith-info, mapped to our field names
_INFO_FIELDS = {
    "الراوي": "narrator",
    "المحدث": "muhaddith",
    "المصدر": "source",
    "الصفحة أو الرقم": "number",
    "خلاصة حكم المحدث": "grade",
}


def search_link(query: str) -> str:
    """Link to the same search on dorar.net, so the user can always check it themselves."""
    return f"https://dorar.net/hadith/search?q={quote(query)}"


def build_query(fragment: str, max_words: int = 7) -> str:
    """Dorar searches work best with a short, distinctive run of words without harakat."""
    words = strip_diacritics(fragment).split()
    return " ".join(words[:max_words])


def parse_dorar_html(html: str) -> list[dict]:
    """Turn Dorar's HTML fragment into a list of hadith dicts.

    Each dict: text, narrator, muhaddith, source, number, grade (any may be "").
    Written defensively: if Dorar changes its markup we return what we can.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    texts = soup.select("div.hadith")
    infos = soup.select("div.hadith-info")
    results = []
    for i, text_div in enumerate(texts):
        text = text_div.get_text(" ", strip=True)
        text = re.sub(r"^\s*\d+\s*-\s*", "", text)          # drop the leading "1 - "
        item = {"text": text, **{v: "" for v in _INFO_FIELDS.values()}}
        if i < len(infos):
            item.update(_parse_info(infos[i]))
        results.append(item)
    return results


def _parse_info(info_div) -> dict:
    """Read "label: value" pairs; a value is everything up to the next label."""
    out, current = {}, None
    for node in info_div.descendants:
        if getattr(node, "name", None) == "span" and "info-subtitle" in (node.get("class") or []):
            label = node.get_text(strip=True).rstrip(":").strip()
            current = _INFO_FIELDS.get(label)
            continue
        if current and isinstance(node, str):
            # skip text that belongs to the label span itself
            if node.parent.name == "span" and "info-subtitle" in (node.parent.get("class") or []):
                continue
            piece = node.strip()
            if piece:
                out[current] = (out.get(current, "") + " " + piece).strip()
    # grades arrive as "[صحيح]" -> "صحيح"
    if "grade" in out:
        out["grade"] = out["grade"].strip("[] ")
    return out


def takhrij(fragment: str) -> dict:
    """Search Dorar for a hadith the sheikh quoted (possibly partially or by meaning).

    Returns {"ok", "query", "results", "search_url", "message"}.
    """
    query = build_query(fragment)
    result = {"ok": False, "query": query, "results": [], "search_url": search_link(query), "message": ""}
    if len(query.split()) < 2:
        result["message"] = "العبارة قصيرة جدًا للبحث"
        return result
    try:
        r = httpx.get(DORAR_API_URL, params={"skey": query}, timeout=DORAR_TIMEOUT,
                      headers={"User-Agent": "Qabas/0.1 (hackathon prototype)"})
        r.raise_for_status()
        html = (r.json().get("ahadith") or {}).get("result", "")
        result["results"] = parse_dorar_html(html)[:5]
        result["ok"] = True
        if not result["results"]:
            # Required behaviour: say nothing was found; never invent a hadith
            result["message"] = "لم يُعثر على حديث مطابق في الدرر السنية"
    except Exception:
        result["message"] = "تعذّر الاتصال بالدرر السنية الآن؛ لا يُعرض نص الحديث دون مصدره. افتح رابط البحث للتحقق."
    return result

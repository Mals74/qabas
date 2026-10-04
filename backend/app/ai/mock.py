"""Mock provider: lets the whole app run without an API key.

It returns the sample lesson for any transcription request and answers
questions with simple keyword retrieval over the sheikh's own words.
Everything downstream (Quran verification, takhrij, card evidence checks)
runs for real on this data.
"""
from rapidfuzz import fuzz

from ..arabic import normalize
from . import consensus
from .sample_data import SAMPLE_CARDS, SAMPLE_SEGMENTS, SAMPLE_SECOND_READING, SAMPLE_SUMMARY
from .timeparse import to_seconds

# Very common words that shouldn't drive retrieval
_STOP = set(normalize("ما من في على عن الى ان او هل هو هي هذا هذه ذلك التي الذي معنى حكم لماذا كيف متى").split())


def _skip(seg: dict) -> bool:
    """Same rule as the Gemini provider: no re-listening for audience or verified verses."""
    from ..quran import verify
    kind = (seg.get("kind") or "").lower()
    if kind == "audience":
        return True
    if kind == "quran":
        m = verify(seg.get("text") or "")
        return bool(m and m.verified)
    return False


class MockProvider:
    name = "mock"

    last_stats: dict = {}

    def transcribe(self, lesson, on_progress=None, context=None) -> list[dict]:
        """Runs the real two-pass logic on the sample: a second 'reading' with a few differences,
        and a scripted re-listen (negations and one unclear word stay unsure, the rest are settled)."""
        if on_progress:
            on_progress("وضع تجريبي: استخدام تفريغ مثال")
        first = [{"start": to_seconds(s), "end": to_seconds(e), "kind": k, "text": t} for s, e, k, t in SAMPLE_SEGMENTS]
        second = [dict(seg, text=SAMPLE_SECOND_READING.get(i, seg["text"])) for i, seg in enumerate(first)]

        def relisten(c0, c1, spots):
            return [{"id": sp.id, "choice": "unsure" if (sp.negation or "الربا" in sp.b_text) else "A", "heard": ""}
                    for sp in spots]

        segments, stats = consensus.run_window(lambda t: first, lambda t: second, relisten, 0, 600,
                                               skip_seg=_skip, max_calls=4)
        self.last_stats = {"windows": 1, "passes": 2, "disagreements": stats["disagreements"],
                           "resolved": stats["resolved"], "uncertain": stats["uncertain"],
                           "low_confidence_windows": int(stats["low_confidence"]), "notes": stats["notes"]}
        return segments

    def summarize(self, transcript_text: str) -> list[dict]:
        return [dict(p) for p in SAMPLE_SUMMARY]

    def cards(self, transcript_text: str) -> list[dict]:
        return [dict(c) for c in SAMPLE_CARDS]

    def pick_hadith(self, items: list[dict]) -> dict[str, list[int]]:
        """Stand-in for the AI check: candidates that share at least 3 words with the quote, best first."""
        out = {}
        for it in items:
            q = set(normalize(it["query"]).split())
            scored = [(len(q & set(normalize(c).split())), n) for n, c in enumerate(it["candidates"], 1)]
            out[str(it["id"])] = [n for sc, n in sorted(scored, reverse=True) if sc >= 3][:3]
        return out

    def ask(self, question: str, context: str, segments_by_lesson: dict) -> dict:
        """Pick the sheikh's sentence that best matches the question's key words."""
        q_words = [w for w in normalize(question).split() if w not in _STOP and len(w) > 2]
        best, best_score = None, 0.0
        for lesson_number, segs in segments_by_lesson.items():
            for seg in segs:
                if seg["kind"] not in ("sharh",):
                    continue
                text = normalize(seg["text"])
                # share of question words present in the segment, softened by fuzzy overlap
                hits = sum(1 for w in q_words if w in text)
                score = (hits / max(len(q_words), 1)) * 70 + fuzz.token_set_ratio(" ".join(q_words), text) * 0.3
                if score > best_score:
                    best, best_score = (lesson_number, seg), score
        if not best or best_score < 45:
            return {"found": False, "personal": False,
                    "answer": "لم أجد جواب هذا السؤال في الدروس المسجلة.", "citations": []}
        lesson_number, seg = best
        return {
            "found": True, "personal": False,
            "answer": seg["text"],
            "citations": [{"lesson_number": lesson_number, "start": seg["start"], "quote": seg["text"]}],
        }

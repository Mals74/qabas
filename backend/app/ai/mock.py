"""Mock provider: lets the whole app run without an API key.

It returns the sample lesson for any transcription request and answers
questions with simple keyword retrieval over the sheikh's own words.
Everything downstream (Quran verification, takhrij, card evidence checks)
runs for real on this data.
"""
from rapidfuzz import fuzz

from ..arabic import normalize
from .sample_data import SAMPLE_CARDS, SAMPLE_SEGMENTS, SAMPLE_SUMMARY
from .timeparse import to_seconds

# Very common words that shouldn't drive retrieval
_STOP = set(normalize("ما من في على عن الى ان او هل هو هي هذا هذه ذلك التي الذي معنى حكم لماذا كيف متى").split())


class MockProvider:
    name = "mock"

    def transcribe(self, lesson, on_progress=None) -> list[dict]:
        if on_progress:
            on_progress("وضع تجريبي: استخدام تفريغ مثال")
        return [
            {"start": to_seconds(s), "end": to_seconds(e), "kind": k, "text": t}
            for s, e, k, t in SAMPLE_SEGMENTS
        ]

    def summarize(self, transcript_text: str) -> list[dict]:
        return [dict(p) for p in SAMPLE_SUMMARY]

    def cards(self, transcript_text: str) -> list[dict]:
        return [dict(c) for c in SAMPLE_CARDS]

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

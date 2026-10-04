"""The lesson API exposes «غير مؤكد» marks and lets the student settle them."""
from fastapi.testclient import TestClient

from app.main import app


def test_sample_lesson_has_marks_and_they_can_be_resolved():
    with TestClient(app) as client:                            # startup seeds the sample lesson
        books = client.get("/api/books").json()
        lesson_id = books[0]["last_lesson"]["id"]
        lesson = client.get(f"/api/lessons/{lesson_id}").json()
        q = lesson["quality"]
        assert q["passes"] == 2 and q["disagreements"] == 3 and q["resolved"] == 1 and q["uncertain"] == 2
        marked = [s for s in lesson["segments"] if s["uncertain"]]
        assert len(marked) == 2
        neg = next(s for s in marked if s["uncertain"][0]["negation"])
        m = neg["uncertain"][0]
        assert neg["text"][m["start"]:m["end"]] == "لا"

        # the student confirms the word was said
        out = client.post(f"/api/segments/{neg['id']}/resolve", json={"mark_id": m["id"], "text": "لا"}).json()
        assert out["uncertain"] == [] and out["corrected"] and "لا تعبدوا" in out["text"]
        # the other one: the student picks the second reading
        other = next(s for s in marked if s["id"] != neg["id"])
        out = client.post(f"/api/segments/{other['id']}/resolve", json={"mark_id": 1, "text": "الربا"}).json()
        assert "كيسير الربا." in out["text"]
        # resolving twice is refused
        assert client.post(f"/api/segments/{other['id']}/resolve", json={"mark_id": 1, "text": "x"}).status_code == 404

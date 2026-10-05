"""A lesson a student adds is visible only on that student's device; the ready-made lessons are visible to all."""
from fastapi.testclient import TestClient

from app import main
from app.ai import limits

A = {"X-Qabas-Owner": "device-aaaaaaaaaaaaaaaa"}
B = {"X-Qabas-Owner": "device-bbbbbbbbbbbbbbbb"}


def test_lessons_and_notes_stay_on_the_device_that_added_them(monkeypatch):
    monkeypatch.setattr(main, "_run_in_background", lambda lesson_id: None)
    monkeypatch.setattr(limits, "lessons", limits.Quota(50))
    with TestClient(main.app) as client:
        shared = {l["id"] for l in client.get("/api/lessons/recent").json()}      # ready-made lessons, no owner
        form = {"title": "درس خاص", "new_book_title": "كتاب خاص", "youtube_url": "https://youtu.be/pjFst8J5hTo"}
        r = client.post("/api/lessons", data=form, headers=A)
        assert r.status_code == 200
        lid = r.json()["id"]

        assert lid in {l["id"] for l in client.get("/api/lessons/recent", headers=A).json()}
        assert lid not in {l["id"] for l in client.get("/api/lessons/recent", headers=B).json()}
        assert client.get(f"/api/lessons/{lid}", headers=B).status_code == 404
        assert client.delete(f"/api/lessons/{lid}", headers=B).status_code == 404
        assert "كتاب خاص" not in [b["title"] for b in client.get("/api/books", headers=B).json()]
        assert client.post("/api/lessons", data=form).status_code == 400              # no device id, no lesson

        # the ready-made lessons: everyone sees them, nobody can delete them, notes on them stay private
        if shared:
            sid = next(iter(shared))
            assert client.get(f"/api/lessons/{sid}", headers=B).status_code == 200
            assert client.delete(f"/api/lessons/{sid}", headers=B).status_code == 403
            client.post(f"/api/lessons/{sid}/notes", json={"start": 1, "text": "ملاحظتي"}, headers=A)
            assert [n["text"] for n in client.get(f"/api/lessons/{sid}", headers=A).json()["notes"]] == ["ملاحظتي"]
            assert client.get(f"/api/lessons/{sid}", headers=B).json()["notes"] == []
        assert client.delete(f"/api/lessons/{lid}", headers=A).status_code == 200

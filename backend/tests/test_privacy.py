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


def test_a_student_can_delete_their_own_notebook_but_not_a_shared_one(monkeypatch):
    monkeypatch.setattr(main, "_run_in_background", lambda lesson_id: None)
    monkeypatch.setattr(limits, "lessons", limits.Quota(50))
    with TestClient(main.app) as client:
        form = {"title": "درس للحذف", "new_book_title": "دفتر للحذف", "youtube_url": "https://youtu.be/pjFst8J5hTo"}
        lid = client.post("/api/lessons", data=form, headers=A).json()["id"]
        bid = client.get(f"/api/lessons/{lid}", headers=A).json()["book_id"]
        client.post(f"/api/lessons/{lid}/notes", json={"start": 1, "text": "ملاحظة"}, headers=A)

        # after deleting its last lesson the notebook is still there, empty, and can be deleted
        assert client.delete(f"/api/lessons/{lid}", headers=A).status_code == 200
        book = client.get(f"/api/books/{bid}", headers=A).json()
        assert book["lessons"] == [] and book["mine"] is True
        assert client.delete(f"/api/books/{bid}", headers=B).status_code == 404       # another device: not found
        assert client.delete(f"/api/books/{bid}", headers=A).status_code == 200
        assert client.get(f"/api/books/{bid}", headers=A).status_code == 404
        assert "دفتر للحذف" not in [b["title"] for b in client.get("/api/books", headers=A).json()]

        # deleting a notebook that still has lessons removes them (and their notes) too
        lid2 = client.post("/api/lessons", data={**form, "new_book_title": "دفتر ثان"}, headers=A).json()["id"]
        bid2 = client.get(f"/api/lessons/{lid2}", headers=A).json()["book_id"]
        client.post(f"/api/lessons/{lid2}/notes", json={"start": 2, "text": "أخرى"}, headers=A)
        assert client.delete(f"/api/books/{bid2}", headers=A).status_code == 200
        assert client.get(f"/api/lessons/{lid2}", headers=A).status_code == 404

        # the ready-made books are not this device's to delete
        for b in client.get("/api/books", headers=B).json():
            full = client.get(f"/api/books/{b['id']}", headers=B).json()
            assert full["mine"] is False
            assert client.delete(f"/api/books/{b['id']}", headers=B).status_code == 403

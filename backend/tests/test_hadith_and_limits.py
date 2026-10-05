"""Hadith lookup (books -> quote rule -> check -> Dorar), the Gemini safety net, the daily budget and shipped lessons."""
import json

import pytest
from sqlmodel import Session, select

from app import config, hadith, hadith_index, pipeline, seed
from app.ai import limits
from app.ai.gemini import BusyError, GeminiProvider, QuotaError, classify_error, pick_backups
from app.ai.mock import MockProvider
from app.db import Book, Card, Lesson, Note, Segment, engine, init_db

NIYYAT = "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى"          # Bukhari 1, quoted almost in full
PARAPHRASE = "حديث الرجل الذي قتل تسعة وتسعين نفسا"                      # by name: the rule cannot settle it
FATIMA = "والله لو أن فاطمة بنت محمد سرقت لقطعت يدها"            # the books say «ابنة محمد … لقطع محمد يدها»


# ---------------- the index ----------------

def test_index_finds_bukhari_1_and_rule_accepts_it():
    idx = hadith_index.get_index()
    assert idx is not None
    cands = idx.candidates(NIYYAT)
    assert cands[0] == "bukhari:1"
    assert idx.quote_rule(NIYYAT, cands[0])
    assert idx.info("bukhari:1")["ref"] == "صحيح البخاري (1)"


def test_rule_needs_five_consecutive_words():
    idx = hadith_index.get_index()
    assert not idx.quote_rule("الأعمال النيات إنما لكل ما نوى", "bukhari:1")     # words present, but never 5 in a row


def test_a_hadith_that_is_not_in_the_books_is_never_accepted_by_the_rule():
    idx = hadith_index.get_index()
    q = "الصبر مفتاح الفرج والعجلة من الشيطان في كل أمر"
    top = idx.candidates(q)[0]
    assert not idx.quote_rule(q, top)


def test_the_fatima_hadith_is_among_the_candidates():
    idx = hadith_index.get_index()
    refs = [idx.info(g)["ref"] for g in idx.candidates(FATIMA)[:3]]
    assert any(r.startswith(("صحيح البخاري", "صحيح مسلم")) for r in refs)


# ---------------- lookup ----------------

def test_rule_result_is_the_books_own_text_with_reference_grade_and_dorar_link():
    r = hadith.takhrij(NIYYAT, provider=None)
    assert r["method"] == "rule" and r["results"][0]["source"] == "صحيح البخاري (1)"
    assert r["results"][0]["origin"] == "books" and "الْأَعْمَالُ" in r["results"][0]["text"]     # with harakat
    assert r["results"][0]["grade"].startswith("صحيح") and r["search_url"].startswith("https://dorar.net/")


def test_without_a_check_the_closest_are_shown_but_marked_unconfirmed():
    r = hadith.takhrij(PARAPHRASE, provider=None)
    assert r["method"] == "candidate" and 1 <= len(r["results"]) <= 3 and "لم يُتأكد" in r["message"]


def test_check_picks_a_candidate():
    class P:
        def pick_hadith(self, items):
            return {it["id"]: [1] for it in items}
    r = hadith.takhrij(PARAPHRASE, provider=P())
    assert r["method"] == "check" and len(r["results"]) == 1


def test_check_saying_none_shows_no_text_and_points_to_dorar():
    class P:
        def pick_hadith(self, items):
            return {it["id"]: [] for it in items}
    r = hadith.takhrij(PARAPHRASE, provider=P())
    assert r["method"] == "none" and r["results"] == [] and "الدرر السنية" in r["message"]


def test_a_failing_check_leaves_candidates_unconfirmed():
    class P:
        def pick_hadith(self, items):
            raise RuntimeError("busy")
    assert hadith.takhrij(PARAPHRASE, provider=P())["method"] == "candidate"


def test_check_answers_are_matched_by_position_whatever_ids_the_model_echoes():
    class P:
        def pick_hadith(self, items):
            assert [it["id"] for it in items] == ["1", "2"]
            return {"المقطع 2": [1], "1": []}
    out = hadith.takhrij_many([("seg-24", PARAPHRASE), ("seg-30", FATIMA)], provider=P())
    assert out["seg-30"]["method"] == "check" and out["seg-24"]["method"] == "none"


def test_quotes_are_checked_in_batches():
    calls = []

    class P:
        def pick_hadith(self, items):
            calls.append(len(items))
            return {it["id"]: [1] for it in items}
    quotes = [(str(i), q) for i, q in enumerate(["حديث الطهور شطر الايمان", "حديث الاخلاص في العمل والنية",
                                                  "حديث المسلم من سلم المسلمون", "حديث الدين النصيحة لله",
                                                  "حديث لا يؤمن احدكم حتى يحب لاخيه"])]
    out = hadith.takhrij_many(quotes, provider=P())
    assert set(out) == {k for k, _ in quotes}
    assert all(n <= 4 for n in calls)                 # at most 4 quotes per request (HADITH_PER_REQUEST)


def test_too_short_a_quote_is_refused():
    assert hadith.takhrij("الحمد", provider=None)["method"] == "none"


def test_a_two_word_reference_by_name_is_searched():
    r = hadith.takhrij("حديث البطاقة", provider=None)
    assert r["method"] == "candidate" and r["results"][0]["source"] in ("سنن ابن ماجه (4300)", "جامع الترمذي (2639)")


# ---------------- the safety net around Gemini ----------------

def _provider():
    p = GeminiProvider.__new__(GeminiProvider)
    p.model, p.light_model, p.backup_calls = "main", "light", 0
    p.models_used, p._busy_until, p._missing, p._light_ok_for_busy = {}, 0.0, set(), False
    p._daily_out, p._found_backups = {}, None
    return p


@pytest.fixture
def fresh_quota(monkeypatch):
    q = limits.Quota(18)
    monkeypatch.setattr(limits, "heavy", q)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(config, "BUSY_BACKUP_MODELS", [])
    return q


@pytest.fixture
def backups(fresh_quota, monkeypatch):
    monkeypatch.setattr(config, "BUSY_BACKUP_MODELS", ["b1", "b2"])
    return fresh_quota


def test_error_kinds():
    assert classify_error(Exception("429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProject")) == "daily"
    assert classify_error(Exception("429 RESOURCE_EXHAUSTED retry in 12s")) == "minute"
    assert classify_error(Exception("503 UNAVAILABLE. This model is currently experiencing high demand")) == "busy"
    assert classify_error(Exception("400 bad request")) == "other"


def test_busy_server_is_retried(fresh_quota):
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        if len(seen) < 3:
            raise Exception("503 UNAVAILABLE")
        return "ok"
    assert p._call(req, heavy=True) == "ok" and seen == ["main", "main", "main"]
    assert fresh_quota.status()["used"] == 3                               # failed attempts count too


def test_daily_limit_switches_to_the_light_model(fresh_quota):
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        if model == "main":
            raise Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return "ok"
    assert p._call(req, heavy=True) == "ok" and seen == ["main", "light"] and p.backup_calls == 1
    assert fresh_quota.status()["exhausted"]
    assert p._call(req, heavy=True) == "ok" and seen[-1] == "light"        # later calls go straight to the light model


def test_both_models_out_of_quota_gives_a_clear_error(fresh_quota):
    p = _provider()

    def req(model):
        raise Exception("429 RESOURCE_EXHAUSTED PerDay")
    with pytest.raises(QuotaError):
        p._call(req, heavy=True)


def test_light_tasks_never_touch_the_main_quota(fresh_quota):
    p, seen = _provider(), []
    p._call(lambda m: seen.append(m) or "ok", heavy=False)
    assert seen == ["light"] and fresh_quota.status()["used"] == 0


def test_own_daily_budget_sends_the_rest_to_the_light_model(monkeypatch):
    monkeypatch.setattr(limits, "heavy", limits.Quota(2))
    monkeypatch.setattr(config, "BUSY_BACKUP_MODELS", [])
    p, seen = _provider(), []
    for _ in range(4):
        p._call(lambda m: seen.append(m) or "ok", heavy=True)
    assert seen == ["main", "main", "light", "light"] and p.backup_calls == 2


def test_overloaded_main_model_moves_to_a_backup_flash_model(backups):
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        if model == "main":
            raise Exception("503 UNAVAILABLE. This model is currently experiencing high demand")
        return "ok"
    assert p._call(req, heavy=True) == "ok"
    assert seen == ["main"] * 3 + ["b1"] and p.models_used == {"b1": 1} and p.backup_calls == 1
    assert backups.status()["used"] == 3                                   # the failed attempts on main are counted
    p._call(req, heavy=True)
    assert seen[-1] == "b1" and seen.count("main") == 3                    # cooldown: main is not asked again


def test_a_backup_name_this_key_cannot_use_is_skipped(backups):
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        if model == "main":
            raise Exception("503 UNAVAILABLE")
        if model == "b1":
            raise Exception("404 NOT_FOUND models/b1 is not found")
        return "ok"
    assert p._call(req, heavy=True) == "ok" and seen[-2:] == ["b1", "b2"]
    p._call(req, heavy=True)
    assert seen.count("b1") == 1                                           # remembered as missing


def test_everything_overloaded_fails_clearly_without_flash_lite(backups):
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        raise Exception("503 UNAVAILABLE")
    with pytest.raises(BusyError):
        p._call(req, heavy=True)
    assert "light" not in seen


def test_daily_limit_prefers_a_backup_flash_model_over_flash_lite(backups):
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        if model == "main":
            raise Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return "ok"
    assert p._call(req, heavy=True) == "ok" and seen == ["main", "b1"]


def test_a_backup_out_of_daily_quota_is_not_asked_again(backups):
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        if model in ("main", "b1"):
            raise Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return "ok"
    p._call(req, heavy=True)
    p._call(req, heavy=True)
    assert seen == ["main", "b1", "b2", "b2"]


def test_notebook_mode_refuses_flash_lite_transcription(fresh_quota, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_LIGHT_TRANSCRIPTION", False)
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        if model == "main":
            raise Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return "ok"
    with pytest.raises(QuotaError):
        p._call(req, heavy=True)
    assert "light" not in seen
    assert p._call(req, heavy=False) == "ok"                               # summary/cards still use Flash-Lite


def test_backups_are_other_numbered_flash_models():
    names = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.0-flash", "gemini-flash-latest",
             "gemini-3.8-flash-lite", "gemini-3.9-flash-preview", "gemini-3.8-pro"]
    assert pick_backups(names, "gemini-3.8-flash") == ["gemini-3.7-flash", "gemini-3.5-flash"]


def test_busy_light_task_fails_clearly(fresh_quota):
    p = _provider()
    with pytest.raises(BusyError):
        p._call(lambda m: (_ for _ in ()).throw(Exception("503 UNAVAILABLE")), heavy=False)


def test_youtube_links_are_made_canonical():
    from app.youtube import canonical
    assert canonical("https://youtu.be/pjFst8J5hTo?si=lYnn7tFvl8vRfX64") == "https://www.youtube.com/watch?v=pjFst8J5hTo"
    assert canonical("https://m.youtube.com/watch?v=mpso_JoPE6M&t=30s") == "https://www.youtube.com/watch?v=mpso_JoPE6M"
    assert canonical("https://www.youtube.com/live/pjFst8J5hTo?feature=share") == "https://www.youtube.com/watch?v=pjFst8J5hTo"
    assert canonical("https://example.com/x") is None


def test_budget_of_zero_means_no_limit():
    q = limits.Quota(0)
    q.record(500)
    assert q.available() and q.status()["left"] is None


# ---------------- a failing summary must not lose the lesson ----------------

class BrokenSummary(MockProvider):
    def summarize(self, text):
        raise RuntimeError("503 busy")


def _new_lesson():
    init_db()
    with Session(engine) as s:
        b = Book(title="كتاب اختبار")
        s.add(b); s.commit(); s.refresh(b)
        l = Lesson(book_id=b.id, title="درس", source_type="youtube", source_url="https://youtu.be/abcdefghijk")
        s.add(l); s.commit(); s.refresh(l)
        return l.id


def test_failed_summary_keeps_the_transcript_and_can_be_retried():
    lid = _new_lesson()
    pipeline.process_lesson(lid, provider=BrokenSummary())
    with Session(engine) as s:
        les = s.get(Lesson, lid)
        assert les.status == "ready" and json.loads(les.quality_json)["summary_failed"]
        assert s.exec(select(Segment).where(Segment.lesson_id == lid)).all()      # transcript kept
        assert s.exec(select(Card).where(Card.lesson_id == lid)).all()            # cards still made
    pipeline.retry_extras(lid, provider=MockProvider())
    with Session(engine) as s:
        les = s.get(Lesson, lid)
        assert "summary_failed" not in json.loads(les.quality_json) and json.loads(les.summary_json)


def test_full_hadith_is_stored_with_the_lesson():
    lid = _new_lesson()
    pipeline.process_lesson(lid, provider=MockProvider())
    with Session(engine) as s:
        h = [x for x in s.exec(select(Segment).where(Segment.lesson_id == lid)).all() if x.kind == "hadith"]
        assert h and all(x.hadith_json for x in h)
        r = json.loads(h[0].hadith_json)
        assert r["method"] in ("rule", "check") and r["results"][0]["source"]


# ---------------- lessons shipped in the repo ----------------

def test_seed_roundtrip(tmp_path, monkeypatch):
    lid = _new_lesson()
    pipeline.process_lesson(lid, provider=MockProvider())
    monkeypatch.setattr(seed, "SEED_DIR", tmp_path)
    with Session(engine) as s:
        seed.write_seed(s, lid, "t")
        n_seg = len(s.exec(select(Segment).where(Segment.lesson_id == lid)).all())
        assert seed.import_seeds(s) == 0                                           # already in the database: not doubled
        for m in (Note, Segment, Card, Lesson, Book):                              # empty database, like a fresh restart
            for row in s.exec(select(m)).all():
                s.delete(row)
        s.commit()
        assert seed.import_seeds(s) == 1
        les = s.exec(select(Lesson)).one()
        assert les.status == "ready" and len(s.exec(select(Segment).where(Segment.lesson_id == les.id)).all()) == n_seg
        assert seed.import_seeds(s) == 0


def test_prepaid_credit_used_up_gives_a_clear_error(fresh_quota):
    p = _provider()
    assert classify_error(Exception("402 Payment Required")) == "credit"
    with pytest.raises(QuotaError, match="الرصيد"):
        p._call(lambda m: (_ for _ in ()).throw(Exception("402 PAYMENT_REQUIRED")), heavy=True)
    with pytest.raises(QuotaError, match="الرصيد"):
        p._call(lambda m: (_ for _ in ()).throw(Exception("402 PAYMENT_REQUIRED")), heavy=False)


def test_daily_lesson_limit_on_the_live_link(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(main, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(main, "_run_in_background", lambda lesson_id: None)
    monkeypatch.setattr(limits, "lessons", limits.Quota(2))
    client = TestClient(main.app, headers={"X-Qabas-Owner": "device-aaaaaaaaaaaaaaaa"})
    form = {"title": "t", "new_book_title": "b", "youtube_url": "https://youtu.be/pjFst8J5hTo"}
    assert client.post("/api/lessons", data=form).status_code == 200
    assert client.post("/api/lessons", data=form).status_code == 200
    r = client.post("/api/lessons", data=form)
    assert r.status_code == 429 and "الميزانية" in r.json()["detail"]
    assert client.get("/api/status").json()["lessons_today"]["left"] == 0


def test_a_failing_relisten_clip_is_not_sent_to_backups(backups):
    p, seen = _provider(), []

    def req(model):
        seen.append(model)
        raise Exception("500 INTERNAL. Internal error encountered.")
    with pytest.raises(BusyError):
        p._call(req, heavy=True, fallback=False)
    assert seen == ["main", "main"]                                        # one retry, no backup models


def test_timestamps_stay_inside_the_window():
    from app.ai.gemini import _fix_offsets
    chunk = [{"start": "9:30", "end": "9:50"}, {"start": "9:50", "end": "10:00:00"}]   # "10:00:00" = 10 minutes
    out = _fix_offsets(chunk, 0, 600)
    assert out[1]["end"] == 600 and out[0]["end"] == 590
    out = _fix_offsets([{"start": "1:00", "end": "5000:00:00"}], 0, 600)              # nonsense: clamped to the window
    assert out[0]["end"] == 600


def test_a_quote_joining_two_surahs_is_verified_as_two_verses():
    from app import quran
    m = quran.verify("قل اعوذ برب الفلق وقل اعوذ برب الناس")
    assert m.verified and [(p["surah_name"], p["ayah_from"]) for p in m.parts] == [("الفلق", 1), ("الناس", 1)]
    one = quran.verify("إذ تستغيثون ربكم فاستجاب لكم")
    assert one.verified and not one.parts and one.surah_name == "الأنفال"


# ---------------- «وفي رواية: …» ----------------

def test_a_variant_wording_is_read_with_the_hadith_before_it():
    r = hadith.takhrij_variant("إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى", "«بالنية»")
    assert r["method"] == "variant" and "بالنية" in r["query"]
    assert "صحيح البخاري" in r["results"][0]["source"]
    assert "بالنيه" in hadith_index.prep(r["results"][0]["text"])
    assert hadith.is_variant_marker("وفي رواية:") and not hadith.is_variant_marker("وفي رواية: بالنية")
    assert hadith.needs_previous("«بالنية»") and not hadith.needs_previous("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى")


def test_a_variant_not_in_the_books_says_so():
    r = hadith.takhrij_variant("إنما الأعمال بالنيات", "وفي رواية: بالمقاصد")
    assert r["method"] == "none" and r["results"] == [] and "الدرر" in r["message"]


def test_a_short_quote_that_is_not_a_variant_is_searched_on_its_own():
    r = hadith.takhrij_variant("إنما الأعمال بالنيات", "حديث جبريل")
    assert r["method"] == "none" and not hadith.keep_variant(r, "حديث جبريل")        # → normal search
    assert hadith.keep_variant(r, "وفي رواية: بالمقاصد")                               # the sheikh said «وفي رواية»

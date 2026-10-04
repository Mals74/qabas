"""Two-pass transcription, re-listening and «غير مؤكد» marks.

Run from the backend folder:  python -m pytest -q
"""
import json
from types import SimpleNamespace

from app.ai import consensus
from app.ai.consensus import apply, clusters, find_spots, looks_broken, run_window
from app.ai.gemini import skip_segment
from app.db import Segment
from app.pipeline import build_segments, resolve_mark

A = [
    {"start": 0, "end": 10, "kind": "sharh", "text": "قال الشيخ: هذا تقدير الدلالة في الاستثناء، لا يتصور في الشرط."},
    {"start": 10, "end": 20, "kind": "sharh", "text": "وقد أطال ابن القيم في إعلام الموقعين."},
    {"start": 20, "end": 25, "kind": "quran", "text": "وما خلقت الجن والانس الا ليعبدون"},
]
B = [
    {"start": 0, "end": 10, "kind": "sharh", "text": "قال الشيخ هذا تقدير الدلالة في الاستثناء يتصور في الشرط"},
    {"start": 10, "end": 20, "kind": "sharh", "text": "فقد أطال ابن القيم في في إعلام الموقعين وهذا مهم."},
    {"start": 20, "end": 25, "kind": "quran", "text": "وما خلقت الجن والانس الا ليعبدوني"},
]


def test_only_meaningful_differences_are_spots():
    spots, _ = find_spots(A, B, skip_seg=skip_segment)
    # و/ف prefix, a repeated word, punctuation and a verified verse are ignored
    assert [(s.a_text, s.b_text) for s in spots] == [("لا", ""), ("", "وهذا مهم.")]
    assert spots[0].negation and not spots[1].negation


def test_unsure_negation_is_kept_and_marked():
    spots, _ = find_spots(A, B, skip_seg=skip_segment)
    for s in spots:
        s.verdict = {"choice": "unsure"}
    out, stats = apply(A, spots)
    seg = out[0]
    mark = seg["uncertain"][0]
    assert seg["text"] == A[0]["text"]                       # pass A kept as is
    assert seg["text"][mark["start"]:mark["end"]] == "لا" and mark["negation"]
    assert stats == {"disagreements": 2, "resolved": 0, "uncertain": 2}


def test_verdicts_patch_the_text_and_keep_offsets_right():
    two = [{"start": 0, "end": 10, "kind": "sharh", "text": "الأول صحيح والثاني خطأ والثالث صحيح والرابع ناقص."}]
    other = [{"start": 0, "end": 10, "kind": "sharh", "text": "الأول صحيح والثاني صواب والثالث باطل والرابع ناقص جدا."}]
    spots, _ = find_spots(two, other)
    verdict = {"خطأ": "B", "صحيح": "unsure", "": "other"}
    for s in spots:
        s.verdict = {"choice": verdict[s.a_text.rstrip(".")] if s.a_text.rstrip(".") in verdict else "unsure", "heard": "تماما"}
    out, _ = apply(two, spots)
    text, marks = out[0]["text"], out[0]["uncertain"]
    assert "والثاني صواب" in text                            # B chosen
    assert [text[m["start"]:m["end"]] for m in marks] == ["صحيح"]   # 'الثالث' spot unsure, offsets still valid


def test_other_answer_that_copies_context_is_ignored():
    spot = find_spots(A, B)[0][0]
    v = consensus.clean_verdict(spot, {"choice": "other", "heard": "قال الشيخ هذا تقدير الدلالة في الاستثناء لا يتصور"})
    assert v["choice"] == "unsure"


def test_loop_and_overlong_output_are_detected():
    assert looks_broken([{"text": "المراد بالفقه هنا الفهم والدين بجميع ابوابه " * 30}], 600).startswith("looped")
    assert looks_broken([{"text": "كلمة " * 5000}], 600).startswith("too long")
    assert looks_broken(A, 25) == ""


def test_spots_are_grouped_into_few_clips():
    spots = [consensus.Spot(i, 0, 0, 0, "a", "b", "", "", t, False) for i, t in enumerate([10, 30, 200, 210, 500, 900, 1100])]
    groups = clusters(spots, 0, 1200, max_calls=3)
    assert len(groups) == 3 and sum(len(g[2]) for g in groups) == 7
    assert all(0 <= c0 < c1 <= 1200 for c0, c1, _ in groups)


def test_broken_pass_falls_back_to_the_healthy_one():
    loop = [{"start": 0, "end": 600, "kind": "sharh", "text": "المراد بالفقه هنا الفهم والدين بجميع ابوابه " * 40}]
    calls = []
    out, stats = run_window(lambda t: calls.append(("A", t)) or loop, lambda t: A, lambda *a: [], 0, 600)
    assert ("A", 0.4) in calls                                # retried once, warmer
    assert out[0]["text"] == A[0]["text"] and stats["notes"]


def test_student_resolves_a_mark():
    seg = Segment(lesson_id=1, idx=0, start=0, text="قال لا يتصور في الشرط ولا في غيره",
                  uncertain_json=json.dumps([{"id": 1, "start": 4, "end": 6, "options": ["لا", ""], "time": 3, "negation": True},
                                             {"id": 2, "start": 26, "end": 28, "options": ["في", "من"], "time": 5, "negation": False}]))
    resolve_mark(seg, 1, "")                                  # nothing was said there
    assert seg.text == "قال يتصور في الشرط ولا في غيره"
    m = json.loads(seg.uncertain_json)
    assert len(m) == 1 and seg.text[m[0]["start"]:m[0]["end"]] == "في" and seg.corrected


def test_build_segments_keeps_valid_marks_only():
    raw = [{"start": 0, "end": 5, "kind": "sharh", "text": "كلام الشيخ هنا",
            "uncertain": [{"start": 0, "end": 4, "options": ["كلام", "سلام"]}, {"start": 50, "end": 60}]},
           {"start": 6, "end": 9, "kind": "quran", "text": "وما خلقت الجن والانس الا ليعبدون",
            "uncertain": [{"start": 0, "end": 3, "options": ["وما", "ما"]}]}]
    segs = build_segments(1, raw)
    assert len(json.loads(segs[0].uncertain_json)) == 1
    assert json.loads(segs[1].uncertain_json) == []           # verified verse: Mushaf text shown, no doubt


# ---------------- the Gemini provider end to end, with a fake client ----------------

class _FakeModels:
    """Answers like Gemini would: pass A, pass B (with context), then verdicts for the re-listen."""
    def __init__(self):
        self.calls = []

    def generate_content(self, model, contents, config):
        prompt = contents.parts[-1].text
        self.calls.append(prompt[:30])
        if "اختلفت نسختان" in prompt:                         # re-listen
            ids = [int(x.split(")")[0]) for x in prompt.split("\n") if x[:1].isdigit()]
            return SimpleNamespace(parsed=[SimpleNamespace(model_dump=lambda i=i: {"id": i, "choice": "unsure", "heard": ""}) for i in ids])
        text = B[0]["text"] if "معلومات تساعدك" in prompt else A[0]["text"]
        seg = SimpleNamespace(model_dump=lambda: {"start": "00:00:01", "end": "00:00:09", "kind": "sharh", "text": text})
        return SimpleNamespace(parsed=[seg])


def test_gemini_provider_two_passes_with_fake_client(monkeypatch):
    from app.ai import gemini
    monkeypatch.setattr(gemini.genai, "Client", lambda api_key: SimpleNamespace(models=_FakeModels()))
    monkeypatch.setattr(gemini, "MAX_CHUNKS", 1)
    p = gemini.GeminiProvider()
    lesson = SimpleNamespace(source_type="youtube", source_url="https://youtu.be/xxxxxxxxxxx", duration_sec=600,
                             sheikh="الشيخ", title="الدرس 1", file_path="")
    segs = p.transcribe(lesson, context={"book": "المختصر"})
    assert len(p.client.models.calls) == 3                     # A, B, one re-listen
    assert segs[0]["uncertain"] and segs[0]["text"][segs[0]["uncertain"][0]["start"]:segs[0]["uncertain"][0]["end"]] == "لا"
    assert p.last_stats["disagreements"] == 1 and p.last_stats["uncertain"] == 1

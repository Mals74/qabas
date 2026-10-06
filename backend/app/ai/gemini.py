"""Gemini provider (google-genai SDK).

- YouTube links are passed to Gemini directly as file_data; the video is never
  downloaded (in line with YouTube's terms). Windows and re-listen clips use start/end offsets.
- Uploaded recordings are cut into windows locally with ffmpeg when it is installed
  (reliable, and each request carries only its own minutes). Without ffmpeg the whole file
  goes through the Files API and the prompt says which minutes to transcribe.
- Each window is transcribed twice (plain, and with book/sheikh context). Where the two
  readings disagree, Gemini listens again to a short clip (see consensus.py).
- Every response is structured JSON (response_schema), then validated by us.
"""
import mimetypes
import re
import shutil
import subprocess
import time
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

from .. import quran
from .. import config
from ..config import (BUSY_COOLDOWN_SEC, CHUNK_MINUTES, GEMINI_API_KEY, GEMINI_MODEL, LIGHT_MODEL, MAX_CHUNKS,
                      MAX_LESSON_MINUTES, RELISTEN_MAX_CALLS, TRANSCRIBE_PASSES)
from . import consensus, limits, prompts
from .timeparse import to_seconds


# ---------- response schemas (what we ask Gemini to return) ----------

class SegmentOut(BaseModel):
    start: str
    end: str
    kind: str
    text: str


class VerdictOut(BaseModel):
    id: int
    choice: str          # A | B | other | unsure
    heard: str


class HadithPickOut(BaseModel):
    query_id: str
    matches: list[int]


class SummaryPointOut(BaseModel):
    point: str
    start: float


class CardOut(BaseModel):
    kind: str
    question: str
    answer: str
    evidence_quote: str
    evidence_start: float


class CitationOut(BaseModel):
    lesson_number: int
    start: float
    quote: str


class AnswerOut(BaseModel):
    found: bool
    personal: bool
    answer: str
    citations: list[CitationOut]


class QuotaError(RuntimeError):
    """Every model this key can use has reached its daily limit."""


class BusyError(RuntimeError):
    """Google's servers stayed overloaded for every model we tried."""


CREDIT_MESSAGE = "انتهى الرصيد المخصص لهذه النسخة التجريبية من خدمة Gemini، فلا يمكن معالجة دروس جديدة الآن. الدروس الموجودة تعمل كما هي."
BUSY_MESSAGE = "تعذّرت المعالجة الآن: خوادم Gemini مزدحمة أو متوقفة مؤقتًا. أعد المحاولة بعد 15 إلى 30 دقيقة."


def classify_error(e: Exception) -> str:
    """credit | daily | minute | busy | missing | other, from the text of a Gemini error."""
    msg = str(e)
    if "402" in msg or "PAYMENT_REQUIRED" in msg or "Payment Required" in msg:
        return "credit"                                    # the prepaid balance is used up (every model stops)
    if "PerDay" in msg or "limit: 0" in msg:
        return "daily"
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "minute"
    if "404" in msg or "NOT_FOUND" in msg or "is not found" in msg or "not supported" in msg:
        return "missing"                                   # this key can't use that model name
    if any(k in msg for k in ("503", "UNAVAILABLE", "500", "INTERNAL", "DEADLINE", "504", "timed out", "Timeout", "overloaded")):
        return "busy"
    return "other"


def pick_backups(names: list[str], main: str, n: int = 2) -> list[str]:
    """The newest other stable Flash models, e.g. gemini-3.7-flash, gemini-3.5-flash (not Lite, not previews/aliases)."""
    found = []
    for name in set(names):
        m = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash", name)
        if m and name != main:
            found.append((float(m.group(1)), name))
    return [name for _, name in sorted(found, reverse=True)[:n]]


def skip_segment(seg: dict) -> bool:
    """Disagreements here don't need re-listening: audience (never stored) and verses that match the Mushaf."""
    kind = (seg.get("kind") or "").lower()
    if kind == "audience":
        return True
    if kind == "quran":
        m = quran.verify(seg.get("text") or "")
        return bool(m and m.verified)
    return False


class _Busy(Exception):
    pass


class _Daily(Exception):
    pass


class _Missing(Exception):
    pass


class GeminiProvider:
    name = "gemini"

    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL              # main model: transcription
        self.light_model = LIGHT_MODEL         # summary, cards, questions, hadith check; also the backup
        self.ffmpeg = shutil.which("ffmpeg")
        self.last_stats: dict = {}
        self.backup_calls = 0                  # requests answered by a model other than the main one
        self.models_used: dict[str, int] = {}  # which models answered the transcription requests
        self._busy_until = 0.0                 # main model overloaded: skip it until this time
        self._missing: set[str] = set()        # backup names this key can't use
        self._daily_out: dict[str, object] = {}  # backup -> quota day on which it said "daily limit reached"
        self._found_backups: Optional[list[str]] = None
        # When every Flash model is overloaded, fail clearly rather than transcribe with Flash-Lite
        self._light_ok_for_busy = False

    # ---------- helpers ----------

    def _config(self, schema, media_low: bool = False, temperature: float = 0, model: str = "") -> types.GenerateContentConfig:
        """Structured-output config. Temperature 0: we want faithful, repeatable output."""
        cfg = dict(response_mime_type="application/json", response_schema=schema, temperature=temperature,
                   http_options=types.HttpOptions(timeout=180_000))
        if media_low:
            # Low video resolution: we only need the audio, and it cuts token use a lot
            cfg["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_LOW
        if (model or self.model).startswith("gemini-2.5-flash"):
            cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)  # transcription needs no reasoning
        return types.GenerateContentConfig(**cfg)

    def _call(self, make_request, heavy: bool, fallback: bool = True):
        """Send one request with the safety net every Gemini call goes through.

        - per-minute limits and short busy spells (503, timeouts): wait and try again
        - main model still overloaded after about a minute: transcription moves to the busy backups
          (another Flash model, own quota) and stays there for BUSY_COOLDOWN_SEC
        - the main model's daily quota used up (or our own daily budget reached): use the light model instead
        - the light model's daily quota used up too: QuotaError; every model overloaded: BusyError
        `make_request(model)` performs the actual request.
        """
        if not heavy:
            try:
                return self._try(make_request, self.light_model, [6, 20, 45, 90])
            except _Busy as e:
                raise BusyError(BUSY_MESSAGE) from e.__cause__
        if not fallback:
            # an optional extra (a re-listen clip): one model, one retry; if it fails the spots stay «غير مؤكد»
            if not limits.heavy.available():
                raise QuotaError("main-model budget used up: re-listen skipped")
            try:
                return self._try(make_request, self.model, [10])
            except (_Busy, _Daily, _Missing) as e:
                raise BusyError("re-listen clip refused by the server") from (e.__cause__ or e)
        chain = [self.model] if limits.heavy.available() else []
        if chain and time.time() < self._busy_until:        # main model was overloaded a moment ago
            chain = []
        today = limits.heavy._today()
        chain += [m for m in self._backups() if m not in self._missing and self._daily_out.get(m) != today]
        busy_seen = False
        for model in chain:
            waits = [15, 40] if model == self.model else [6, 20]   # Google counts failed attempts too: keep them few
            try:
                resp = self._try(make_request, model, waits)
            except _Busy:
                busy_seen = True
                if model == self.model:
                    self._busy_until = time.time() + BUSY_COOLDOWN_SEC
                continue
            except _Missing:
                self._missing.add(model)
                continue
            except _Daily:
                if model == self.model:
                    limits.heavy.mark_exhausted()
                else:
                    self._daily_out[model] = today      # don't ask it again until the quota day changes
                continue
            if model != self.model:
                self.backup_calls += 1
            self.models_used[model] = self.models_used.get(model, 0) + 1
            return resp
        if busy_seen and not self._light_ok_for_busy:
            raise BusyError(BUSY_MESSAGE)
        # daily quotas gone (or nothing else usable): the light model is the last resort
        if not config.ALLOW_LIGHT_TRANSCRIPTION:
            raise QuotaError("الحد اليومي المجاني لنماذج Flash استُهلك، والتفريغ بنموذج Flash-Lite غير مفعّل. "
                             "جرّب بعد الساعة 10 صباحًا بتوقيت السعودية.")
        self.backup_calls += 1
        try:
            resp = self._try(make_request, self.light_model, [6, 20, 45])
        except _Busy as e:
            raise BusyError(BUSY_MESSAGE) from e.__cause__
        self.models_used[self.light_model] = self.models_used.get(self.light_model, 0) + 1
        return resp

    def _backups(self) -> list[str]:
        """Busy/daily backups for transcription: set by GEMINI_BUSY_BACKUPS, or the newest other Flash models."""
        if config.BUSY_BACKUP_MODELS is not None:
            return config.BUSY_BACKUP_MODELS
        if self._found_backups is None:
            try:
                names = [m.name.split("/")[-1] for m in self.client.models.list()]
            except Exception:
                names = []
            self._found_backups = pick_backups(names, self.model)
            print("[gemini] transcription backups:", self._found_backups or "none", flush=True)
        return self._found_backups

    def _try(self, make_request, model: str, waits: list[int]):
        """One model, with waits for per-minute limits and busy spells. Raises _Busy/_Daily/_Missing to the chain."""
        for attempt in range(len(waits) + 1):
            if model == self.model:
                if not limits.heavy.available():          # retries used up our own daily budget
                    raise _Daily()
                limits.heavy.record()                     # every attempt counts, failed or not (as in Google's dashboard)
            try:
                return make_request(model)
            except Exception as e:
                kind = classify_error(e)
                print(f"[gemini] {model}: {kind} - {str(e)[:120]}", flush=True)   # shows in the server log / notebook
                if kind in ("minute", "busy") and attempt < len(waits):
                    m = re.search(r"retry in ([\d.]+)s", str(e))
                    time.sleep(min(float(m.group(1)) + 2, 70) if m else waits[attempt])
                    continue
                if kind == "credit":
                    raise QuotaError(CREDIT_MESSAGE) from e
                if kind == "daily":
                    if model == self.light_model:
                        raise QuotaError("الحد اليومي المجاني لخدمة Gemini استُهلك الآن. جرّب بعد الساعة 10 صباحًا بتوقيت السعودية.") from e
                    raise _Daily() from e
                if kind in ("busy", "minute"):
                    raise _Busy() from e
                if kind == "missing" and model != self.light_model:
                    raise _Missing() from e
                raise

    def _generate(self, parts: list, schema, temperature: float = 0, media_low: bool = True, heavy: bool = True,
                  fallback: bool = True):
        return self._call(lambda model: self.client.models.generate_content(
            model=model, contents=types.Content(parts=parts),
            config=self._config(schema, media_low=media_low, temperature=temperature, model=model)), heavy, fallback)

    def _text(self, prompt: str, schema, heavy: bool = False):
        """A text-only request. Light by default: it must not spend the main model's daily quota."""
        return self._call(lambda model: self.client.models.generate_content(
            model=model, contents=prompt, config=self._config(schema, model=model)), heavy)

    # ---------- media ----------

    def _duration(self, path: str) -> float:
        probe = shutil.which("ffprobe")
        if not probe:
            return 0
        r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except ValueError:
            return 0

    def _cut(self, path: str, start: float, end: float) -> types.Part:
        """A piece of a local recording as mono 16 kHz MP3 bytes (small enough to send inline)."""
        r = subprocess.run([self.ffmpeg, "-v", "error", "-ss", f"{start:.2f}", "-t", f"{max(1, end - start):.2f}",
                            "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", "-f", "mp3", "pipe:1"],
                           capture_output=True, check=True)
        return types.Part.from_bytes(data=r.stdout, mime_type="audio/mp3")

    def _upload(self, lesson) -> tuple[types.Part, bool]:
        """Whole file through the Files API (used when ffmpeg is not available)."""
        mime = mimetypes.guess_type(lesson.file_path)[0] or "audio/mpeg"
        uploaded = self.client.files.upload(file=lesson.file_path)
        while getattr(uploaded.state, "name", str(uploaded.state)) == "PROCESSING":
            time.sleep(3)
            uploaded = self.client.files.get(name=uploaded.name)
        return types.Part(file_data=types.FileData(file_uri=uploaded.uri, mime_type=mime)), mime.startswith("video/")

    def _clip_factory(self, lesson):
        """Returns clip(start, end) -> (media part, times_are_relative, note for the prompt, really_clipped)."""
        if lesson.source_type == "youtube":
            def clip(start, end):
                part = types.Part(file_data=types.FileData(file_uri=lesson.source_url),
                                  video_metadata=types.VideoMetadata(start_offset=f"{int(start)}s", end_offset=f"{int(end)}s"))
                return part, False, f"هذا الجزء من الثانية {int(start)} إلى الثانية {int(end)} من الفيديو.", True
            return clip, None
        if self.ffmpeg:
            def clip(start, end):
                return self._cut(lesson.file_path, start, end), True, "هذا المقطع جزء من الدرس؛ اكتب التوقيت من بداية هذا المقطع.", True
            return clip, self._duration(lesson.file_path) or None
        whole, is_video = self._upload(lesson)

        def clip(start, end):
            part = whole
            if is_video:
                part = types.Part(file_data=whole.file_data,
                                  video_metadata=types.VideoMetadata(start_offset=f"{int(start)}s", end_offset=f"{int(end)}s"))
                return part, False, f"هذا الجزء من الثانية {int(start)} إلى الثانية {int(end)} من الفيديو.", True
            return part, False, f"فرّغ فقط الجزء من الثانية {int(start)} إلى الثانية {int(end)} من التسجيل.", False
        return clip, None

    # ---------- provider API ----------

    def transcribe(self, lesson, on_progress=None, context: Optional[dict] = None) -> list[dict]:
        """Transcribe the whole lesson window by window. Returns raw segment dicts (with 'uncertain' marks)."""
        say = on_progress or (lambda m: None)
        clip, known_duration = self._clip_factory(lesson)
        duration = lesson.duration_sec or known_duration or 0
        cap = MAX_LESSON_MINUTES * 60 if MAX_LESSON_MINUTES else 0
        capped = bool(cap) and (not duration or duration > cap)
        if cap:                                        # the live demo processes at most the first minutes of a recording
            duration = min(duration, cap) if duration else cap
        window = min(CHUNK_MINUTES * 60, cap) if cap else CHUNK_MINUTES * 60
        self.backup_calls = 0
        self.models_used = {}
        ctx = prompts.CONTEXT.format(book=(context or {}).get("book", ""), sheikh=lesson.sheikh or "",
                                     title=lesson.title or "")
        segments: list[dict] = []
        totals = {"windows": 0, "disagreements": 0, "resolved": 0, "uncertain": 0, "low_confidence_windows": 0,
                  "passes": TRANSCRIBE_PASSES, "notes": [], "capped_minutes": MAX_LESSON_MINUTES if capped else 0}

        for n in range(MAX_CHUNKS):
            lo, hi = n * window, (n + 1) * window
            if duration and lo >= duration:
                break
            if duration:
                hi = min(hi, duration)
            part, relative, note, _ = clip(lo, hi)

            def one_pass(temperature, with_context, label):
                say(f"تفريغ الجزء {n + 1} ({label})")
                prompt = prompts.TRANSCRIBE.format(offset_note=note) + (ctx if with_context else "")
                resp = self._generate([part, types.Part(text=prompt)], list[SegmentOut], temperature)
                chunk = [s.model_dump() for s in (resp.parsed or [])]
                return _fix_offsets(chunk, lo, window, relative)

            try:
                if TRANSCRIBE_PASSES >= 2:
                    def relisten(c0, c1, group):
                        clip_part, _, _, clipped = clip(c0, c1)
                        # a whole uploaded file can't be cut without ffmpeg: give times from its start instead
                        prompt = consensus.relisten_prompt(group, c0 if clipped else 0)
                        resp = self._generate([clip_part, types.Part(text=prompt)], list[VerdictOut], fallback=False)
                        return [v.model_dump() for v in (resp.parsed or [])]
                    chunk, stats = consensus.run_window(
                        lambda t: one_pass(t, False, "القراءة الأولى"),
                        lambda t: one_pass(t, True, "القراءة الثانية"),
                        relisten, lo, hi, skip_seg=skip_segment, max_calls=RELISTEN_MAX_CALLS, on_progress=say)
                    for k in ("disagreements", "resolved", "uncertain"):
                        totals[k] += stats[k]
                    totals["low_confidence_windows"] += int(stats["low_confidence"])
                    totals["notes"] += [f"window {n + 1}: {x}" for x in stats["notes"]]
                else:
                    chunk = one_pass(0, False, "قراءة واحدة")
            except (QuotaError, BusyError) as e:
                if n > 0:                                # keep the windows already transcribed
                    totals["notes"].append(f"stopped at window {n + 1}: {'daily limit' if isinstance(e, QuotaError) else 'servers busy'}")
                    break
                raise
            except Exception as e:
                # Asking past the end of a video raises an error: treat as "done" after the first window
                if n > 0:
                    totals["notes"].append(f"stopped at window {n + 1}: {str(e)[:80]}")
                    break
                raise
            if not chunk:
                break                                   # silence / end of recording
            totals["windows"] += 1
            segments.extend(chunk)
            if lesson.source_type == "youtube" and not duration and len(chunk) < 3:
                break                                   # very short tail -> probably the end
        totals["backup_calls"] = self.backup_calls        # requests answered by a model other than the main one
        totals["models_used"] = dict(self.models_used)
        self.last_stats = totals
        return segments

    def summarize(self, transcript_text: str) -> list[dict]:
        resp = self._text(prompts.SUMMARY.format(transcript=transcript_text), list[SummaryPointOut])
        return [p.model_dump() for p in (resp.parsed or [])]

    def cards(self, transcript_text: str) -> list[dict]:
        resp = self._text(prompts.CARDS.format(transcript=transcript_text), list[CardOut])
        return [c.model_dump() for c in (resp.parsed or [])]

    def pick_hadith(self, items: list[dict]) -> dict[str, list[int]]:
        """Which candidate is the hadith the sheikh meant? items: [{id, query, candidates: [text, ...]}].

        Returns {id: [candidate numbers, best first]}; an empty list means "none of them".
        """
        blocks = []
        for it in items:
            lines = [f"### المقطع {it['id']}: «{it['query']}»"]
            lines += [f"{n}) {c}" for n, c in enumerate(it["candidates"], 1)]
            blocks.append("\n".join(lines))
        resp = self._text(prompts.HADITH_CHECK.format(blocks="\n\n".join(blocks)), list[HadithPickOut])
        return {str(p.query_id): list(p.matches) for p in (resp.parsed or [])}

    def ask(self, question: str, context: str, segments_by_lesson: Optional[dict] = None) -> dict:
        """Long-context Q&A: the book's full transcripts go into the prompt (no chunking/embeddings)."""
        resp = self._text(prompts.ASK.format(context=context, question=question), AnswerOut)
        return resp.parsed.model_dump() if resp.parsed else {"found": False, "personal": False, "answer": "", "citations": []}


def _fix_offsets(chunk: list[dict], start: int, window: int, relative: bool = False) -> list[dict]:
    """Make every timestamp absolute (seconds from the start of the recording).

    For clips cut locally the times are relative to the clip, so we always add the start.
    Otherwise we ask for absolute times, but if all times fall inside [0, window] while this
    window starts later, the model clearly used clip-relative times: shift them.
    """
    for s in chunk:
        s["start"] = to_seconds(s.get("start"))
        s["end"] = to_seconds(s.get("end")) or s["start"]
    if start > 0 and chunk and (relative or max(s["start"] for s in chunk) <= window):
        for s in chunk:
            s["start"] += start
            s["end"] += start
    return _clamp_times(chunk, start, start + window)


def _plausible(t: float, lo: float, hi: float) -> float:
    """A time outside this window is a misread format: "10:00:00" meant 10:00, not 10 hours."""
    for cand in (t, t / 60, t / 3600):
        if lo - 5 <= cand <= hi + 5:
            return cand
    return min(max(t, lo), hi)


def _clamp_times(chunk: list[dict], lo: float, hi: float) -> list[dict]:
    """Keep every timestamp inside the window, in order, with end >= start."""
    prev = lo
    for s in chunk:
        s["start"] = max(prev, min(_plausible(s["start"], lo, hi), hi))
        s["end"] = max(s["start"], min(_plausible(s["end"], lo, hi), hi))
        prev = s["start"]
    return chunk

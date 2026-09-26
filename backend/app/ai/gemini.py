"""Gemini provider (google-genai SDK).

- YouTube links are passed to Gemini directly as file_data; the video is never
  downloaded (in line with YouTube's terms).
- Uploaded recordings go through the Files API.
- Long lessons are transcribed in windows (CHUNK_MINUTES) to stay within output limits.
- Every response is structured JSON (response_schema), then validated by us.
"""
import mimetypes
import time
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

from ..config import CHUNK_MINUTES, GEMINI_API_KEY, GEMINI_MODEL, MAX_CHUNKS
from . import prompts
from .timeparse import to_seconds


# ---------- response schemas (what we ask Gemini to return) ----------

class SegmentOut(BaseModel):
    start: str
    end: str
    kind: str
    text: str


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


class GeminiProvider:
    name = "gemini"

    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GEMINI_MODEL

    # ---------- helpers ----------

    def _config(self, schema, media_low: bool = False) -> types.GenerateContentConfig:
        """Structured-output config. Temperature 0: we want faithful, repeatable output."""
        cfg = dict(response_mime_type="application/json", response_schema=schema, temperature=0)
        if media_low:
            # Low video resolution: we only need the audio, and it cuts token use a lot
            cfg["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_LOW
        if self.model.startswith("gemini-2.5-flash"):
            cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)  # transcription needs no reasoning
        return types.GenerateContentConfig(**cfg)

    def _media_part(self, lesson) -> tuple[types.Part, bool]:
        """Returns (part, is_video). Uploads local files once via the Files API."""
        if lesson.source_type == "youtube":
            return types.Part(file_data=types.FileData(file_uri=lesson.source_url)), True
        mime = mimetypes.guess_type(lesson.file_path)[0] or "audio/mpeg"
        uploaded = self.client.files.upload(file=lesson.file_path)
        # Wait until Google finishes processing the file
        while getattr(uploaded.state, "name", str(uploaded.state)) == "PROCESSING":
            time.sleep(3)
            uploaded = self.client.files.get(name=uploaded.name)
        part = types.Part(file_data=types.FileData(file_uri=uploaded.uri, mime_type=mime))
        return part, mime.startswith("video/")

    # ---------- provider API ----------

    def transcribe(self, lesson, on_progress=None) -> list[dict]:
        """Transcribe the whole lesson window by window. Returns raw segment dicts."""
        media, is_video = self._media_part(lesson)
        window = CHUNK_MINUTES * 60
        segments: list[dict] = []
        for n in range(MAX_CHUNKS):
            start, end = n * window, (n + 1) * window
            if lesson.duration_sec and start >= lesson.duration_sec:
                break
            if on_progress:
                on_progress(f"تفريغ الجزء {n + 1}")
            part = media
            if is_video:
                # Clip the video server-side to this window
                part = types.Part(file_data=media.file_data,
                                  video_metadata=types.VideoMetadata(start_offset=f"{start}s", end_offset=f"{end}s"))
            note = f"هذا الجزء من الثانية {start} إلى الثانية {end} من الفيديو."
            if not is_video:
                note += " فرّغ هذا الجزء فقط."
            prompt = prompts.TRANSCRIBE.format(offset_note=note)
            try:
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=types.Content(parts=[part, types.Part(text=prompt)]),
                    config=self._config(list[SegmentOut], media_low=True),
                )
            except Exception as e:
                # Asking past the end of a video raises an error: treat as "done" after the first window
                if n > 0:
                    break
                raise
            chunk = [s.model_dump() for s in (resp.parsed or [])]
            if not chunk:
                break                                   # silence / end of recording
            chunk = _fix_offsets(chunk, start, window)
            segments.extend(chunk)
            if lesson.source_type == "youtube" and not lesson.duration_sec and len(chunk) < 3:
                break                                   # very short tail -> probably the end
        return segments

    def summarize(self, transcript_text: str) -> list[dict]:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompts.SUMMARY.format(transcript=transcript_text),
            config=self._config(list[SummaryPointOut]),
        )
        return [p.model_dump() for p in (resp.parsed or [])]

    def cards(self, transcript_text: str) -> list[dict]:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompts.CARDS.format(transcript=transcript_text),
            config=self._config(list[CardOut]),
        )
        return [c.model_dump() for c in (resp.parsed or [])]

    def ask(self, question: str, context: str, segments_by_lesson: Optional[dict] = None) -> dict:
        """Long-context Q&A: the book's full transcripts go into the prompt (no chunking/embeddings)."""
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompts.ASK.format(context=context, question=question),
            config=self._config(AnswerOut),
        )
        return resp.parsed.model_dump() if resp.parsed else {"found": False, "personal": False, "answer": "", "citations": []}


def _fix_offsets(chunk: list[dict], start: int, window: int) -> list[dict]:
    """Make every timestamp absolute (seconds from the start of the recording).

    We ask for absolute times, but if all times fall inside [0, window] while this
    window starts later, the model clearly used clip-relative times: shift them.
    """
    for s in chunk:
        s["start"] = to_seconds(s.get("start"))
        s["end"] = to_seconds(s.get("end")) or s["start"]
    if start > 0 and chunk and max(s["start"] for s in chunk) <= window:
        for s in chunk:
            s["start"] += start
            s["end"] += start
    return chunk

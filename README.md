# قَبَس — Qabas (hackathon prototype)

Turns a lesson (YouTube link or recording) into an organized notebook per book:
timestamped transcript, matn linked to sharh, Quran verses checked against the Mushaf
text, hadith takhrij from Dorar, evidence-checked review cards, and "ask the lessons"
with citations to the lesson and minute.

**Principle:** the AI proposes, the trusted source confirms.

## What is real vs. sample

| Part | Status |
|---|---|
| Quran verification (normalization + fuzzy match against the Uthmani text) | Real, tested (`backend/tests`) |
| Hadith takhrij (Dorar API) | Real code; needs internet. If Dorar is unreachable, no hadith text is shown, only a search link |
| Review cards evidence check, citation check, audience redaction | Real, tested |
| Transcription, summary, cards, Q&A with Gemini | Real code, runs when `GEMINI_API_KEY` is set |
| Without a key (mock mode) | Every new lesson gets the same sample transcript, clearly labelled |
| Sample lesson "كتاب التوحيد - الدرس 1" | Illustrative text written for the demo, not any sheikh's words |

## Run on Replit

1. Create a Repl → Import → upload this folder (or push it to GitHub and import).
2. Tools → Secrets → add `GEMINI_API_KEY` (from https://aistudio.google.com/apikey). Never paste the key in code or chat.
3. Press **Run**. `start.sh` installs packages, builds the frontend and starts the server.
4. Optional secrets: `GEMINI_MODEL` (default `gemini-2.5-flash`; change it if Google retires that name),
   `CHUNK_MINUTES` (default 20), `DATABASE_URL` (PostgreSQL later).

## Run locally

```bash
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000     # API + built app on :8000
cd ../frontend && npm install && npm run dev            # optional: hot-reload UI on :5173
cd ../backend && python -m pytest -q                    # tests
```

## How it works

```
YouTube link / recording
   │  Gemini (file_data = YouTube URL, no download; Files API for uploads), 20-min windows
   ▼
timestamped segments: matn | sharh | quran | hadith | audience | other
   ├─ quran    → matched to the Uthmani text (arabic.py + quran.py); the Mushaf text is displayed
   ├─ hadith   → Dorar search on demand (hadith.py); full text only from Dorar
   ├─ audience → replaced by a placeholder (attendees' words are never stored)
   └─ sharh    → linked to the matn line it explains
summary (labelled ملخص آلي) · review cards (kept only if the quote exists in the sheikh's words)
ask the lessons: whole book in the model's long context → citations verified against the transcript
```

## Files

- `backend/app/quran.py` — verse verification (the core accuracy piece)
- `backend/app/hadith.py` — Dorar client and parser
- `backend/app/pipeline.py` — lesson processing, card checks, grounded Q&A, search
- `backend/app/ai/` — Gemini provider, mock provider, prompts, sample data
- `frontend/src/` — React app (RTL), screens follow the design mockups
- `SOURCES.md` — draft sources and licenses log (challenge terms, Clause 9)

## Known limits (prototype)

- The Gemini path is written against the google-genai SDK but was not run end-to-end in the build
  environment (no key / no access to Google). Test it first with a short lesson.
- Dorar's HTML format was parsed from its documented structure; check the first live results.
- The Quran text comes from the quran-json package (QuranEnc Uthmani text). If you prefer Tanzil,
  replace `backend/data/quran_uthmani.json` with the same structure.
- No user accounts yet: this is a single private notebook.

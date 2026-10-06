# قَبَس — Qabas

> **أسهل طريقة للتجربة: الرابط المباشر** — **https://qabas-ncea.onrender.com**
> لا يحتاج إلى مفتاح، والدروس الجاهزة متاحة فورًا، ويمكن إضافة حتى 5 دروس جديدة يوميًا (لأسباب تتعلق بالميزانية).
>
> ملاحظة: الخادم المجاني ينام بعد 15 دقيقة دون زوار، فقد يستغرق الفتح الأول نحو دقيقة. / The free server sleeps when idle; the first visit may take about a minute.
>
> **The easiest way to try Qabas is the live link: https://qabas-ncea.onrender.com** — no key needed; the ready-made lessons open instantly.
> To run it from the source code you need **your own Google Gemini API key** (free at https://aistudio.google.com/apikey):
> copy `.env.example` to `.env`, put the key in it, then run one of the commands below.
> Without a key the app still starts: the ready-made lessons, verse checks and hadith word search work; new lessons need the key.

**Storage.** Locally the app uses SQLite (`backend/data/qabas.db`). The live link stores lessons and notes in a free
Neon Postgres database: set `DATABASE_URL` to its connection string (`postgresql://…`); without it, Render's free
disk is wiped on every restart. Lessons a student adds are visible only on the device that added them.

### Run it yourself

```bash
git clone <this repo> && cd qabas
cp .env.example .env            # paste your GEMINI_API_KEY into .env
docker build -t qabas . && docker run -p 8000:8000 --env-file .env qabas
# open http://localhost:8000
```

Without Docker (Python 3.11+, Node 20+, ffmpeg):

```bash
cd frontend && npm ci && npm run build && cd ../backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000       # open http://localhost:8000
python -m pytest -q                              # 58 tests, no key needed
```


Turns a lesson (YouTube link or recording) into an organized notebook per book:
timestamped transcript, matn linked to sharh, Quran verses checked against the Mushaf
text, the full hadith from nine hadith books with its reference and grade (and a link to verify it on Dorar), evidence-checked review cards, and "ask the lessons"
with citations to the lesson and minute.

**Principle:** the AI proposes, the trusted source confirms.

## What is real vs. sample

| Part | Status |
|---|---|
| Quran verification (normalization + fuzzy match against the Uthmani text) | Real, tested (`backend/tests`) |
| Hadith search: Haystack BM25 over nine hadith books (the two Sahihs, the four Sunan, the Muwatta, the Nawawi and Qudsi Forty) → quote rule (5 consecutive words) → Flash-Lite check, with a "check on Dorar" link | Real, tested (`backend/tests`, and 111 questions in `notebooks/`). The book's own text is shown with its reference and grade, never AI text. If nothing is confirmed, the closest candidates are shown marked "unconfirmed". Dorar's API refuses requests from other servers and sites (Cloudflare), so we link to Dorar for verification instead of calling it |
| Review cards evidence check, citation check, audience redaction | Real, tested |
| Two-pass transcription: disagreements re-listened, the rest marked «غير مؤكد» | Real, tested with a fake Gemini client and on real transcripts; the sample lesson shows it in mock mode |
| Transcription, summary, cards, Q&A with Gemini | Real code, runs when `GEMINI_API_KEY` is set |
| Without a key (mock mode) | Every new lesson gets the same sample transcript, clearly labelled |
| Sample lesson "كتاب التوحيد - الدرس 1" | Illustrative text written for the demo, not any sheikh's words |

## Free-tier safety (live demo)

The free Gemini quota is small (about 20 requests a day for the main model) and is shared by everyone who opens the link.

- **Model split:** 3.8 Flash only for transcription; summary, cards, questions and the hadith check use `GEMINI_LIGHT_MODEL` (Flash-Lite), which has its own quota.
- **Budget:** the live demo runs on a small **prepaid** Gemini credit (set in AI Studio → Billing; when it reaches $0 Google stops every request with "402", which the app reports clearly while existing lessons keep working). On top of that the app allows `MAX_LESSONS_PER_DAY` new lessons a day (default 5, shown on the upload page) and at most `MAX_LESSON_MINUTES` of each recording (default 10), so visitors can't use up the credit in one go.
- **Safety net:** busy servers (503) and per-minute limits are retried for about a minute; if the main model stays overloaded, transcription moves to a backup Flash model (`GEMINI_BUSY_BACKUPS`; by default the newest other numbered `gemini-X.Y-flash` models the key can use, each with its own quota; aliases such as `gemini-flash-latest` share the main model's quota and are avoided) and skips the main model for 10 minutes. When the main model's daily quota is used up (or our own `HEAVY_DAILY_LIMIT` budget (default 200, set for the paid tier) is reached) the backups are tried first (a backup that says "daily limit" is not asked again that day), then the light model — unless `ALLOW_LIGHT_TRANSCRIPTION=0`, which the demo-lesson notebook sets. Flash-Lite is never used because of busy servers (2–3× more transcription errors in our tests): if everything is overloaded, the lesson stops with a clear "try again in 10–15 minutes" message. The quality note names the models that answered; if the summary or cards fail, the transcript is kept and a "retry" button appears.
- **Cap:** at most `MAX_LESSON_MINUTES` (default 10) of each recording is processed.
- **Real lessons shipped in the repo:** `python -m app.seed process …` (see `notebooks/qabas_process_lessons.ipynb`) runs the real pipeline once and saves `backend/data/seed/<name>.json`; the app loads these at startup, so visitors open real lessons without any request. Set `SHOW_SAMPLE=0` to hide the labelled demo lesson.

## Run on Replit

1. Create a Repl → Import → upload this folder (or push it to GitHub and import).
2. Tools → Secrets → add `GEMINI_API_KEY` (from https://aistudio.google.com/apikey). Never paste the key in code or chat.
3. Press **Run**. `start.sh` installs packages, builds the frontend and starts the server.
4. Optional secrets: `GEMINI_MODEL` (default `gemini-3.8-flash`; change it if Google retires that name),
   `CHUNK_MINUTES` (default 20), `DATABASE_URL` (PostgreSQL later),
   `TRANSCRIBE_PASSES` (default 2; set 1 to save requests on the free tier: single reading, no re-listening),
   `RELISTEN_MAX_CALLS` (default 4 short re-listen requests per window).
5. Recommended: install **ffmpeg** (on Replit: add `pkgs.ffmpeg` to the Nix packages). Uploaded recordings are then
   cut into windows and short re-listen clips locally; without it the whole file is sent and the prompt names the minutes.

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
   │  Gemini (file_data = YouTube URL, no download; uploads cut with ffmpeg or sent via the Files API), 20-min windows
   │  each window read twice: plain prompt, and with book/sheikh/title context (ai/consensus.py)
   │    ├─ both readings aligned word by word; meaningless differences ignored (و/ف, spelling, repeats, false starts)
   │    ├─ real disagreements (negations first) → Gemini re-listens to short clips and decides
   │    ├─ still unsure → kept as spoken in reading 1, marked «غير مؤكد» for the student (tap → listen → choose)
   │    └─ a reading that loops or is far too long → retried once, then the healthy reading is used
   ▼
timestamped segments: matn | sharh | quran | hadith | audience | other
   ├─ quran    → matched to the Uthmani text (arabic.py + quran.py); the Mushaf text is displayed
   ├─ hadith   → the sheikh's words kept exactly as said; Dorar search on demand shows the verified text beside them
   ├─ audience → replaced by a placeholder (attendees' words are never stored)
   └─ sharh    → linked to the matn line it explains
summary (labelled ملخص آلي) · review cards (kept only if the quote exists in the sheikh's words)
ask the lessons: whole book in the model's long context → citations verified against the transcript
```

## Files

- `backend/app/quran.py` — verse verification (the core accuracy piece)
- `backend/app/hadith.py`, `hadith_index.py` — hadith search: BM25 over the books, quote rule, AI check, Dorar link
- `backend/tools/build_hadith_corpus.py` — builds `data/hadith_corpus.json.gz` from fawazahmed0/hadith-api
- `backend/app/pipeline.py` — lesson processing, card checks, grounded Q&A, search
- `backend/app/ai/` — Gemini provider, two-pass consensus (`consensus.py`), mock provider, prompts, sample data
- `frontend/src/` — React app (RTL), screens follow the design mockups
- `SOURCES.md` — the Islamic sources (name, issuing body, link, use) and the components and licenses log

## Known limits (prototype)

- The Gemini path is written against the google-genai SDK but was not run end-to-end in the build
  environment (no key / no access to Google). Test it first with a short lesson.
- Dorar's HTML format was parsed from its documented structure; check the first live results.
- Displayed verses: the King Fahd Glorious Quran Printing Complex's official digital Mushaf data, UthmanicHafs v2.0
  (2022-09-07), downloaded from https://download.qurancomplex.gov.sa/resources_dev/UthmanicHafs_v2-0.zip
  (SHA-256 a7b0e559…dfd72c), copied as is into `backend/data/quran_kfgqpc.json` and shown in the Complex's own
  font (`frontend/public/fonts/uthmanic_hafs_v20.ttf`).
- الفهرس (word meanings): the dictionary table of the Jawami' al-Kalim database (Offok, published free by Islamweb;
  classical texts in the public domain), via https://huggingface.co/datasets/angryreply/jawami3_alkalem — الصحاح،
  القاموس المحيط، لسان العرب، تهذيب اللغة; 12,787 roots in `backend/data/fahras.db.gz`.
  The root of a tapped word is found by morphology rules (`backend/app/fahras.py`), no AI.
  Matching uses `backend/data/quran_uthmani.json` (quran-json package, QuranEnc Uthmani text).
- No user accounts yet: this is a single private notebook.

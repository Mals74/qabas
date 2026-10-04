"""Builds qabas_eval_v2.ipynb: 6 published lessons (3 Al-Khudair, 3 Ibn Baz), Gemini only."""
import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

CORE = open("eval_core2.py", encoding="utf-8").read()   # tested offline

cells = []
md = lambda s: cells.append(new_markdown_cell(s.strip()))
code = lambda s: cells.append(new_code_cell(s.strip()))

md(r"""
# Qabas — transcription evaluation v2 (6 published lessons)

Tests Gemini on 6 lessons that already have an official transcript, so nothing has to be transcribed by hand:

| Clip | Sheikh | Lesson |
|---|---|---|
| K1–K3 | Abdulkarim Al-Khudair | شرح متن الورقات في أصول الفقه (02, 03, 04) |
| B1–B3 | Abdulaziz Ibn Baz | شرح المنتقى (كتاب الصلاة), كتاب التوحيد, شرح المنتقى (أول الكتاب) |

For each lesson the notebook downloads the MP3 and the transcript from the sheikh's official site,
keeps the **first 10 minutes** of audio, transcribes it with Gemini (plain, with book info, and with two kinds of glossary), runs the negation check,
and scores everything. It finds the matching part of the transcript on its own (no manual trimming).

**Metrics** (after removing harakat and unifying letters)
- **WER** word error rate, **CER** letter error rate. Lower is better.
- **Negation errors**: places where a negation word (لا، لم، لن، ما، ليس، غير…) differs from the transcript
  (a different و/ف prefix alone does not count).
- Scoring ignores honorific phrases (رضي الله عنه، رحمه الله…) and treats numbers written as digits and spoken as words as equal,
  because the official transcripts add, drop or abbreviate these freely.
  This is the meaning-changing error we care about most.

**Note:** the official transcripts are lightly edited (fillers and repeats removed), so the prompt asks
Gemini for the same "clean" style. Some remaining differences are editing choices, not mistakes.

## Steps

1. The `GEMINI_API_KEY` secret from last time is still in your Colab account. If not: key icon (Secrets) →
   Add new secret → name `GEMINI_API_KEY` → paste the key → turn on **Notebook access**.
2. **Runtime → Run all.** Nothing to upload.
3. Check the preview printed by **section 4**: each clip should show a lesson title, an MP3 link,
   a transcript of thousands of words, and a first line that matches the lesson.
4. Wait. Sections 7–10 call Gemini about 35 times (roughly 10–15 minutes). The free tier allows about 20 per day for
   the transcription model: if a cell stops with "Daily quota … used up", run the notebook again the next day
   (section 4b keeps everything in Drive), or enable billing on the key's Google Cloud project.
   If a cell stops on an error, just run it again: finished transcripts are kept and skipped.
5. At the end a file **`qabas_eval_v2_results.zip`** downloads. Send it back.
""")

md("## 1. Install packages")
code(r"""
# google-genai: Gemini | jiwer: WER/CER | beautifulsoup4: read the lesson pages | pandas: tables
!pip -q install -U google-genai jiwer pandas beautifulsoup4
!ffmpeg -version | head -n 1
""")

md("## 2. Load the API key from Colab Secrets")
code(r"""
import os                                              # environment variables
from google.colab import userdata                      # Colab's Secrets panel

try:
    os.environ["GEMINI_API_KEY"] = userdata.get("GEMINI_API_KEY")   # read the secret
    print("Gemini key loaded ✔")
except Exception:
    print("Could not read GEMINI_API_KEY. Add it in the Secrets panel (key icon) and enable Notebook access.")
    raise
""")

md("## 3. Scoring code (text cleanup, auto-trim, negation check)")
code(CORE)

md("""
## 4. Download the lessons and preview them

Check each block: title, MP3 link, transcript size and first words.
If one clip fails, replace its URL with one of the backups listed in the cell and run it again.
""")
code(r"""
import json, pathlib, subprocess, time                   # files, ffmpeg, pauses
import requests                                          # download pages and audio

CLIP_MINUTES = 10                                        # audio length tested per lesson
OUT = pathlib.Path("qabas_eval_v2"); OUT.mkdir(exist_ok=True)

CLIPS = [
    {"id": "K1", "sheikh": "الشيخ عبد الكريم بن عبد الله الخضير", "book": "متن الورقات في أصول الفقه لإمام الحرمين الجويني",
     "url": "https://shkhudheir.com/scientific-lesson/1518818146",
     "mp3_alt": "https://archive.org/download/al-warakat/warakat_02.mp3",
     "prev": "https://shkhudheir.com/scientific-lesson/680686512"},      # previous lesson = 01
    {"id": "K2", "sheikh": "الشيخ عبد الكريم بن عبد الله الخضير", "book": "متن الورقات في أصول الفقه لإمام الحرمين الجويني",
     "url": "https://shkhudheir.com/scientific-lesson/1376454418", "prev": "K1",
     "mp3_alt": "https://archive.org/download/al-warakat/warakat_03.mp3"},
    {"id": "K3", "sheikh": "الشيخ عبد الكريم بن عبد الله الخضير", "book": "متن الورقات في أصول الفقه لإمام الحرمين الجويني",
     "url": "https://shkhudheir.com/scientific-lesson/2145156569", "prev": "K2",
     "mp3_alt": "https://archive.org/download/al-warakat/warakat_04.mp3"},
    {"id": "B1", "sheikh": "الشيخ عبد العزيز بن عبد الله بن باز", "book": "المنتقى من أخبار المصطفى، كتاب الصلاة",
     "url": "https://binbaz.org.sa/audios/336/%D9%83%D8%AA%D8%A7%D8%A8-%D8%A7%D9%84%D8%B5%D9%84%D8%A7%D8%A9"},
    {"id": "B2", "sheikh": "الشيخ عبد العزيز بن عبد الله بن باز", "book": "كتاب التوحيد للشيخ محمد بن عبد الوهاب",
     "url": "https://binbaz.org.sa/audios/2021/08-%D8%A8%D8%A7%D8%A8-%D8%AA%D9%81%D8%B3%D9%8A%D8%B1-%D8%A7%D9%84%D8%AA%D9%88%D8%AD%D9%8A%D8%AF-%D9%88%D8%B4%D9%87%D8%A7%D8%AF%D8%A9-%D8%A7%D9%86-%D9%84%D8%A7-%D8%A7%D9%84%D9%87-%D8%A7%D9%84%D8%A7-%D8%A7%D9%84%D9%84%D9%87"},
    {"id": "B3", "sheikh": "الشيخ عبد العزيز بن عبد الله بن باز", "book": "المنتقى من أخبار المصطفى لمجد الدين أبي البركات ابن تيمية، كتاب الطهارة",
     "url": "https://binbaz.org.sa/audios/1985/01-%D9%85%D9%86-%D8%AD%D8%AF%D9%8A%D8%AB-%D9%87%D9%88-%D8%A7%D9%84%D8%B7%D9%87%D9%88%D8%B1-%D9%85%D8%A7%D9%88%D9%87-%D8%A7%D9%84%D8%AD%D9%84-%D9%85%D9%8A%D8%AA%D8%AA%D9%87"},
]
# mp3_alt: shkhudheir.com redirects its MP3 links to the home page, so Al-Khudair's audio comes from the
# same series on archive.org (lesson numbers assumed to match the site: check "Matched" in the results).
# The transcript still comes from his official site.
# Backups if a page fails (paste into "url" of the failing clip):
#   Al-Khudair الورقات (01): https://shkhudheir.com/scientific-lesson/680686512
#   Ibn Baz كتاب التوحيد 01: https://binbaz.org.sa/audios/2016/01-%D8%A8%D8%A7%D8%A8-%D9%83%D8%AA%D8%A7%D8%A8-%D8%A7%D9%84%D8%AA%D9%88%D8%AD%D9%8A%D8%AF

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/126.0 Safari/537.36", "Accept": "*/*"}


SESSION = requests.Session()                             # keeps the site's cookies between page and MP3
SESSION.headers.update(HEADERS)


def candidates(url):
    # the link as written, then without the invisible RTL marks (%E2%80%AB) in the file name
    out = [url, url.replace("%E2%80%AB", ""), url.replace("\u202b", "")]
    return list(dict.fromkeys(out))


def download(url, dest, referer):
    # stream the MP3 to disk; if the server answers with a web page, say which page it was
    last = ""
    for u in candidates(url):
        with SESSION.get(u, headers={"Referer": referer, "Range": "bytes=0-"}, timeout=(30, 300),
                         stream=True, allow_redirects=True) as r:
            kind = r.headers.get("Content-Type", "?")
            hops = " → ".join(str(h.status_code) for h in r.history)
            print(f"   try …{u[-45:]}: HTTP {r.status_code}{' (after ' + hops + ')' if hops else ''}, {kind}")
            if r.ok and "html" not in kind:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                return
            body = r.text[:5000] if "html" in kind else ""
            m = re.search(r"<title>(.*?)</title>", body, re.S)
            last = f"got a web page instead of audio (final URL: {r.url[:90]} | page title: {m.group(1).strip()[:70] if m else '-'})"
    raise RuntimeError(last)


def duration(path):
    # length of an audio file in seconds
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


for c in CLIPS:
    d = OUT / c["id"]; d.mkdir(exist_ok=True)
    print(f"━━━━ {c['id']} ━━━━")
    try:
        html = SESSION.get(c["url"], timeout=60).text                            # lesson page (sets cookies)
        from bs4 import BeautifulSoup
        t = BeautifulSoup(html, "html.parser").title
        c["title"] = t.get_text().strip() if t else ""                          # page title
        c["mp3"] = c.get("mp3_alt") or find_mp3(html, c["url"])                    # audio link
        ref = clean_reference(main_text(html))                                    # transcript text
        (d / "reference_full.txt").write_text(ref, encoding="utf-8")
        full = d / "full.mp3"
        if not full.exists() or full.stat().st_size < 100_000:                  # download once
            download(c["mp3"], full, c["url"])
        clip = d / "clip.mp3"                                                     # first 10 min, mono 16 kHz
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(full), "-t", str(CLIP_MINUTES * 60),
                        "-ac", "1", "-ar", "16000", "-b:a", "32k", str(clip)], check=True)
        c["seconds"] = duration(clip)
        c["ok"] = len(normalize(ref).split()) > 1000 and c["seconds"] > 60
        print("Title     :", c["title"][:110])
        print("MP3       :", c["mp3"])
        print(f"Audio     : {duration(full)/60:.0f} min lesson → using first {c['seconds']/60:.1f} min")
        print(f"Transcript: {len(normalize(ref).split()):,} words")
        print("Starts    :", " ".join(ref.split()[:30]))
        print("OK ✔" if c["ok"] else "⚠ Something looks wrong: check the title and transcript above")
    except Exception as e:
        c["ok"] = False
        print("⚠ FAILED:", repr(e))
        print("  MP3 link:", c.get("mp3", "?"))
        print(f"  → Manual fix: open the MP3 link in your browser and save the file, then in Colab's")
        print(f"    Files panel (folder icon) upload it into qabas_eval_v2/{c['id']}/ and rename it to full.mp3.")
        print("    Run this cell again: it will use your file.")
    print()

json.dump(CLIPS, open(OUT / "clips.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
READY = [c for c in CLIPS if c.get("ok")]
print(f"{len(READY)}/{len(CLIPS)} clips ready:", ", ".join(c["id"] for c in READY))
""")

md("""
## 4b. Save results to Google Drive

The free Gemini tier allows about 20 requests per model per day, and this notebook needs about 30,
so it may take two days. This cell keeps everything in your Drive so nothing is lost overnight.
Finished transcripts are skipped when you run the notebook again.
""")
code(r"""
# Keep all results in Google Drive so they survive a runtime reset (the free quota may need 2 days)
import shutil
from google.colab import drive

drive.mount("/content/drive")                                       # asks for permission once
DRIVE_OUT = pathlib.Path("/content/drive/MyDrive/qabas_eval_v2")
if pathlib.Path("qabas_eval_v2").exists():                          # copy what this runtime already has
    shutil.copytree("qabas_eval_v2", DRIVE_OUT, dirs_exist_ok=True, ignore=shutil.ignore_patterns("full.mp3"))
DRIVE_OUT.mkdir(parents=True, exist_ok=True)
OUT = DRIVE_OUT                                                     # every later cell now reads and writes here
done = sorted(p.relative_to(OUT).as_posix() for p in OUT.glob("*/[ABCD]*.txt"))
print("Saving to", OUT, "| transcripts already done:", ", ".join(done) or "none")
""")

md("""
## 5. Gemini setup

The audio clip (about 2.4 MB) is sent directly with the request, so nothing is uploaded to YouTube or Drive.
""")
code(r"""
import re, time                                         # parse wait times from errors
from google import genai                                # Gemini SDK
from google.genai import types                          # request types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3.8-flash"                              # model under test (same as earlier runs)

names = [m.name.split("/")[-1] for m in client.models.list() if "gemini" in m.name]
print("Available:", ", ".join(sorted(names)))
assert MODEL in names, f"{MODEL} is not available to this key; pick one from the list above"
# Glossaries are plain text work: use a Flash-Lite model so they don't use MODEL's daily quota
GLOSS_MODEL = next((n for n in sorted(names, reverse=True) if "flash-lite" in n and "preview" not in n), MODEL)
print("Transcription model:", MODEL, "| glossary model:", GLOSS_MODEL)


class DailyQuotaError(RuntimeError):
    pass


def _call(model, contents, cfg, attempts=4):
    # one request with sensible handling of rate limits
    for i in range(attempts):
        try:
            r = client.models.generate_content(model=model, contents=contents, config=types.GenerateContentConfig(**cfg))
            time.sleep(3)                                # stay under the per-minute limit
            return r
        except Exception as e:
            msg = str(e)
            if "PerDay" in msg:                          # daily free quota used up: retrying won't help
                raise DailyQuotaError(
                    f"Daily quota for {model} is used up. Everything finished so far is saved. "
                    "Run this cell again after the quota resets (midnight Pacific time), or enable billing.") from None
            m = re.search(r"retry in ([\d.]+)s", msg)    # per-minute limit: wait as long as Google says
            wait = float(m.group(1)) + 3 if m else 20 * (i + 1)
            print(f"   retry {i+1} in {wait:.0f}s: {msg[:120]}")
            time.sleep(wait)
    raise RuntimeError("Gemini failed 4 times")


def ask_gemini(audio_path, prompt, schema=None, temperature=0):
    # send an audio file + prompt, return the text answer
    audio = types.Part.from_bytes(data=pathlib.Path(audio_path).read_bytes(), mime_type="audio/mp3")
    cfg = dict(temperature=temperature, max_output_tokens=16384,
               automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    if schema:                                           # JSON answer for the negation check
        cfg.update(response_mime_type="application/json", response_schema=schema)
    if MODEL.startswith("gemini-2.5-flash"):
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    r = _call(MODEL, types.Content(parts=[audio, types.Part(text=prompt)]), cfg)
    fr = str(r.candidates[0].finish_reason) if r.candidates else "?"
    if "MAX_TOKENS" in fr:
        print("   ⚠ output was cut off (MAX_TOKENS)")
    return r.text or ""


def ask_text(prompt, schema=None, model=None):
    # text-only request (used to build glossaries)
    cfg = dict(temperature=0, max_output_tokens=4096,
               automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    if schema:
        cfg.update(response_mime_type="application/json", response_schema=schema)
    return _call(model or GLOSS_MODEL, prompt, cfg).text or ""
""")

md("""
## 6. Prompts

- **A (plain)**: rules only.
- **B (context)**: same rules plus the book, sheikh and lesson title.

The rules ask for a *clean* transcript (no fillers or repeats) because that is how the official transcripts
are written, and they include the new negation rule.
""")
code(r"""
RULES = '''فرّغ الكلام في هذا المقطع الصوتي باللغة العربية من بدايته إلى نهايته، كما يُفرَّغ الدرس العلمي للنشر:
- اكتب كل الجمل بألفاظ المتكلم نفسها، دون تلخيص أو إعادة صياغة أو حذف جملة.
- احذف فقط: التأتأة، وكلمات الحشو، والتكرار غير المقصود، وبداية الكلمة أو الجملة التي قطعها المتكلم وأعادها.
- إذا صحّح المتكلم نفسه فاكتب الصيغة التي استقر عليها.
- أدوات النفي والاستثناء (لا، لم، لن، ما، ليس، غير، إلا) اكتبها كما نُطقت تمامًا؛ حذفها أو زيادتها يقلب المعنى.
- اكتب قراءة القارئ للمتن، وكلام الشيخ، وأسئلة الحاضرين.
- لا تُكمل آية أو حديثًا من حفظك؛ اكتب ما نُطق فقط.
- اكتب النص فقط: دون توقيت أو عناوين أو أسماء متحدثين، ودون تشكيل.'''


def prompt_for(c, with_context, glossary=None):
    if not with_context:
        return RULES
    p = RULES + f'''

معلومات تساعدك على كتابة الأسماء والمصطلحات بإملائها الصحيح (استخدمها فقط لما نُطق فعلًا، ولا تُضف منها شيئًا):
- الشيخ: {c["sheikh"]}
- الكتاب: {c["book"]}
- عنوان الدرس: {c.get("title", "")}'''
    if glossary:
        p += "\n- أعلام وكتب ومصطلحات قد ترد في الدرس: " + "، ".join(glossary)
    return p

print(RULES)
""")

md("""
## 7. Transcribe (2 passes per clip)

Every transcript is checked for two failure modes seen with Flash-Lite: **looping** (the same passage written again
and again) and **far too many words** for the audio length. A broken transcript is retried once; if it is still broken
it is kept but marked, and left out of the averages.
""")
code(r"""
def transcribe_to(c, prompt, f):
    # transcribe the clip into file f, retry once if the output looks broken
    text = ask_gemini(OUT / c["id"] / "clip.mp3", prompt)
    why = looks_broken(text, c["seconds"])
    if why:
        print(f"   ⚠ {why} → retrying once")
        retry = ask_gemini(OUT / c["id"] / "clip.mp3", prompt, temperature=0.4)
        why_retry = looks_broken(retry, c["seconds"])
        if not why_retry:
            text, why = retry, ""
        else:
            why = why_retry
    f.write_text(text, encoding="utf-8")
    flag = f.with_suffix(".broken")
    if why:
        flag.write_text(why, encoding="utf-8"); print(f"   ✖ still broken ({why}); marked and left out of averages")
    elif flag.exists():
        flag.unlink()
    print(f"   {len(text.split())} words")


for c in READY:
    d = OUT / c["id"]
    for tag, ctx in [("A", False), ("B", True)]:
        f = d / f"{tag}.txt"
        if f.exists():                                   # already done (re-run safe)
            print(c["id"], tag, "already done"); continue
        print(f"▶ {c['id']} pass {tag} …")
        transcribe_to(c, prompt_for(c, ctx), f)
""")

md("""
## 8. Build glossaries

- **Best case (C)**: Gemini lists the names, books and terms found in the official transcript of *this same clip*.
  This is deliberately "cheating": it is the best context possible. The same list is used to score name/term accuracy.
- **Realistic (D, Al-Khudair only)**: the list is built from the *previous lesson's* official transcript,
  which is what the app would already have when a student adds a new lesson.
""")
code(r"""
GLOSS_PROMPT = '''فيما يلي نص من درس علمي شرعي. استخرج منه أهم الأعلام (أسماء الأشخاص)، وأسماء الكتب، والأماكن،
والمصطلحات العلمية الخاصة بهذا الفن، كما كُتبت في النص تمامًا. لا تذكر الكلمات العامة، ولا تكرر عنصرًا.
أعد قائمة JSON بحد أقصى {n} عنصرًا، الأهم فالأهم.

النص:
{text}'''
LIST_SCHEMA = {"type": "ARRAY", "items": {"type": "STRING"}}


def glossary_from(text, n=40):
    # ask Gemini for the names/books/terms in a text
    out = json.loads(ask_text(GLOSS_PROMPT.format(n=n, text=text[:60000]), schema=LIST_SCHEMA))
    return [t.strip() for t in out if t and t.strip()][:n]


def previous_text(c):
    # official transcript of the previous lesson (another clip's page, or a URL)
    prev = c.get("prev")
    if not prev:
        return ""
    if prev.startswith("http"):
        f = OUT / c["id"] / "prev_reference.txt"
        if not f.exists():
            f.write_text(clean_reference(main_text(requests.get(prev, headers=HEADERS, timeout=60).text)), encoding="utf-8")
        return f.read_text(encoding="utf-8")
    f = OUT / prev / "reference_full.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""


for c in READY:
    d = OUT / c["id"]
    gf = d / "glossaries.json"
    if gf.exists():
        c["gloss"] = json.loads(gf.read_text(encoding="utf-8")); print(c["id"], "glossaries already built"); continue
    ref_full = (d / "reference_full.txt").read_text(encoding="utf-8")
    span = raw_span(ref_full, (d / "A.txt").read_text(encoding="utf-8"))    # transcript part that matches the clip
    g = {"oracle": glossary_from(span)}
    prev = previous_text(c)
    g["previous"] = glossary_from(prev) if prev else []
    gf.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    c["gloss"] = g
    print(f"━━ {c['id']}\n  best case ({len(g['oracle'])}): " + "، ".join(g["oracle"]))
    if g["previous"]:
        print(f"  from previous lesson ({len(g['previous'])}): " + "، ".join(g["previous"]))
""")

md("## 9. Transcribe with the glossaries (C for all clips, D for Al-Khudair)")
code(r"""
for c in READY:
    d = OUT / c["id"]
    jobs = [("C", c["gloss"]["oracle"])] + ([("D", c["gloss"]["previous"])] if c["gloss"]["previous"] else [])
    for tag, gl in jobs:
        f = d / f"{tag}.txt"
        if f.exists():
            print(c["id"], tag, "already done"); continue
        print(f"▶ {c['id']} pass {tag} ({len(gl)} glossary items) …")
        transcribe_to(c, prompt_for(c, True, gl), f)
""")

md("""
## 10. Negation check (A vs B)

Wherever A and B disagree about a negation word, Gemini listens again to ±45 seconds around that spot
and says which version was actually said. A is then corrected → **A + check**.
""")
code(r"""
WINDOW = 45
MAX_SPOTS = 15                                                # more than this means one version is unreliable
CHECK_PROMPT = '''استمع إلى هذا الجزء من الدرس. اختلفت نسختان من التفريغ في الموضع التالي، والاختلاف يتعلق بأداة نفي قد تقلب المعنى:

...{before} [النسخة A: {A}] [النسخة B: {B}] {after}...

ابحث عن هذه الجملة في الصوت واستمع إليها بدقة، وانتبه لوجود أداة النفي أو غيابها.
- إن طابقت النسخة A ما قيل فعلًا فأجب choice = "A"
- إن طابقت النسخة B فأجب choice = "B"
- إن لم تطابق أيّ منهما فأجب choice = "other" واكتب في heard الكلمات التي قيلت مكان الموضع المختلف فقط.'''
SCHEMA = {"type": "OBJECT", "properties": {"choice": {"type": "STRING", "enum": ["A", "B", "other"]},
                                           "heard": {"type": "STRING"}}, "required": ["choice", "heard"]}
report = []
for c in READY:
    d = OUT / c["id"]
    if (d / "A_checked.txt").exists():
        print(c["id"], "already checked"); continue
    A, B = (d / "A.txt").read_text(encoding="utf-8"), (d / "B.txt").read_text(encoding="utf-8")
    if (d / "A.broken").exists() or (d / "B.broken").exists():
        print(f"━━ {c['id']}: skipped (A or B is broken, comparing them would add errors)")
        (d / "A_checked.txt").write_text(A, encoding="utf-8"); continue
    spots = diff_spots(A, B)
    print(f"━━ {c['id']}: {len(spots)} negation disagreement(s)")
    if len(spots) > MAX_SPOTS:                                # A and B differ too much to be trusted
        print(f"   more than {MAX_SPOTS}: skipped")
        (d / "A_checked.txt").write_text(A, encoding="utf-8"); continue
    verdicts = {}
    for s in spots:
        t = s["pos"] * c["seconds"]                           # estimated time of the spot
        s0, s1 = max(0, int(t - WINDOW)), min(int(c["seconds"]), int(t + WINDOW))
        win = d / f"spot{s['id']}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(s0), "-t", str(s1 - s0),
                        "-i", str(d / "clip.mp3"), str(win)], check=True)
        try:
            v = json.loads(ask_gemini(win, CHECK_PROMPT.format(**s), schema=SCHEMA))
        except Exception as e:
            v = {"choice": "unsure", "heard": str(e)[:80]}
        n_span = max(len(s["A"].split()), len(s["B"].split()))
        if v.get("choice") == "other" and len(v.get("heard", "").split()) > n_span + 3:
            v = {"choice": "unsure", "heard": v.get("heard", "")}  # answer too long: it copied context, not the spot
        verdicts[s["id"]] = v
        line = (f"{c['id']} #{s['id']} [{s0//60}:{s0%60:02d}–{s1//60}:{s1%60:02d}] ...{s['before']} "
                f"[A: {s['A']}] [B: {s['B']}] {s['after']}...\n   → {v['choice']}"
                + (f" | heard: {v['heard']}" if v["choice"] == "other" else ""))
        print(line); report.append(line)
    (d / "A_checked.txt").write_text(apply_verdicts(A, spots, verdicts), encoding="utf-8")
if report:
    (OUT / "negation_check_report.txt").write_text("\n\n".join(report), encoding="utf-8")
""")

md("""
## 11. Final results

- **Terms**: share of the names/books/terms (best-case list) that each system wrote correctly. This is the number
  context is supposed to move; WER barely shows it.
- Rows: **A** plain · **B** book/sheikh/title · **C** + best-case glossary · **D** + glossary from the previous lesson · **A + check**.
""")
code(r"""
import pandas as pd

SYSTEMS = [("A", "A plain"), ("B", "B context"), ("C", "C best-case glossary"),
           ("D", "D previous-lesson glossary"), ("A_checked", "A + check")]


def score_row(c, name, hyp_text):
    ref_full = (OUT / c["id"] / "reference_full.txt").read_text(encoding="utf-8")
    r, h, info = auto_trim(ref_full, hyp_text)
    s, t = wer_cer(r, h), term_scores(r, h, c["gloss"]["oracle"])
    return {"Clip": c["id"], "System": name, "WER": s["WER"], "CER": s["CER"],
            "Terms": t["terms_pct"], "Missed terms": "، ".join(t["missed_terms"]),
            "Negation errors": len(diff_spots(r, h)),
            "Words out": info.get("hyp_words", 0), "Ref words used": info.get("ref_used", 0),
            "Matched": "yes" if info["ok"] else "NO"}


def flags(c, tag, row):
    # broken output, or output that covers a very different amount of the transcript (skipped or invented text)
    base = "A" if tag == "A_checked" else tag
    b = OUT / c["id"] / f"{base}.broken"
    if b.exists():
        return "broken: " + b.read_text(encoding="utf-8")
    ratio = row["Ref words used"] / max(row["Words out"], 1)
    return "check: covers %.0f%% of its length" % (100 * ratio) if not 0.75 <= ratio <= 1.25 else ""


rows = []
for c in READY:
    for tag, name in SYSTEMS:
        f = OUT / c["id"] / f"{tag}.txt"
        if f.exists():
            row = score_row(c, name, f.read_text(encoding="utf-8"))
            row["Flag"] = flags(c, tag, row)
            rows.append(row)
final = pd.DataFrame(rows)
final.to_csv(OUT / "results.csv", index=False, encoding="utf-8-sig")


def summarize(df):
    w = df["Ref words used"]
    return pd.Series({"Clips": len(df), "WER": (df.WER * w).sum() / w.sum(), "CER": (df.CER * w).sum() / w.sum(),
                      "Terms": df.Terms.mean(), "Negation errors": df["Negation errors"].sum(), "Words": w.sum()})


fmt = {"WER": "{:.1%}", "CER": "{:.1%}", "Terms": "{:.0%}"}
ok = final[~final.Flag.str.startswith("broken")]                # broken transcripts are left out of averages
print("Left out as broken:", ", ".join(final[final.Flag.str.startswith("broken")].apply(lambda r: f"{r.Clip} {r.System}", axis=1)) or "none")
summary = ok.groupby("System", sort=False).apply(summarize)
summary.to_csv(OUT / "summary.csv", encoding="utf-8-sig")
print("All clips (D exists only for Al-Khudair, so compare it using the second table):")
display(summary.style.format(fmt))
k = ok[ok.Clip.str.startswith("K")]
if len(k):
    summary_k = k.groupby("System", sort=False).apply(summarize)
    summary_k.to_csv(OUT / "summary_khudair.csv", encoding="utf-8-sig")
    print("Al-Khudair clips only:")
    display(summary_k.style.format(fmt))
display(final.drop(columns="Missed terms").style.format(fmt))
""")

md("## 12. Error details and download")
code(r"""
from google.colab import files

for c in READY:
    d = OUT / c["id"]
    ref_full = (d / "reference_full.txt").read_text(encoding="utf-8")
    lines = [f"=== {c['id']} | {c.get('title', '')} ===",
             "Best-case glossary: " + "، ".join(c["gloss"]["oracle"]),
             "Previous-lesson glossary: " + ("، ".join(c["gloss"]["previous"]) or "-")]
    for tag, _ in SYSTEMS:
        f = d / f"{tag}.txt"
        if not f.exists():
            continue
        r, h, _ = auto_trim(ref_full, f.read_text(encoding="utf-8"))
        t = term_scores(r, h, c["gloss"]["oracle"])
        lines.append(f"\n--- {tag}: missed terms: " + ("، ".join(t["missed_terms"]) or "none"))
        lines.append(f"--- {tag}: negation differences vs official transcript ---")
        lines += [f"  ...{s['before']} [ref: {s['A']}] [model: {s['B']}] {s['after']}..." for s in diff_spots(r, h)]
        lines.append(f"--- {tag}: top word swaps (official → model) ---")
        lines += [f"  {a} → {b}  ×{n}" for (a, b), n in top_substitutions(r, h, 12)]
    (d / "errors.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]), "\n")

import zipfile                                            # zip text results only (audio stays in Colab)
with zipfile.ZipFile("qabas_eval_v2_results.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob("*"):
        if p.suffix in {".txt", ".csv", ".json"}:
            z.write(p, p.relative_to(OUT))
files.download("qabas_eval_v2_results.zip")
""")

nb = new_notebook(cells=cells, metadata={"colab": {"provenance": []},
                                         "kernelspec": {"name": "python3", "display_name": "Python 3"}})
nbformat.write(nb, "qabas_eval_v2.ipynb")
print("notebook written with", len(cells), "cells")

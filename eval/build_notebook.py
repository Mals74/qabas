"""Builds qabas_transcription_eval.ipynb from the cells below (run once)."""
import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

CORE = open("eval_core.py", encoding="utf-8").read()   # scoring code, tested locally

cells = []
md = lambda s: cells.append(new_markdown_cell(s.strip()))
code = lambda s: cells.append(new_code_cell(s.strip()))

md(r"""
# Qabas — transcription evaluation (clip01)

This notebook measures how accurately each system transcribes a 10-minute lesson clip,
against your hand-made transcript.

| System | What it is |
|---|---|
| **Gemini plain** | Gemini with a simple "transcribe verbatim" prompt |
| **Gemini + context** | Same, plus book, sheikh and the glossary of names/terms |
| **Whisper** *(optional)* | Whisper large-v3 running on Colab's GPU |
| **Whisper + names** *(optional)* | Whisper with the names given as a prompt |

**Metrics** (all computed after removing harakat and unifying letters):
- **WER**: word error rate. Lower is better (0.10 = 10% of words wrong).
- **CER**: letter error rate. Lower is better.
- **Terms (unique)**: how many of the different names/terms came out right at least once.
- **Terms (occurrences)**: share of all their occurrences reproduced correctly.

## Before you start (one time)

1. **Get a Gemini API key**: https://aistudio.google.com/apikey
2. In this notebook, click the **key icon (Secrets)** in the left sidebar, then **Add new secret**:
   - Name: `GEMINI_API_KEY`
   - Value: your key
   - Turn on **Notebook access**.

   Never paste the key into a cell.
3. Have **`clip01.zip`** ready (reference.txt, terms.txt, glossary.txt, clip.json).
4. *(Only for Whisper)* **Runtime → Change runtime type → T4 GPU**, and have the lesson's audio file ready.

## Do I need to download the video?

- **Gemini: no.** The code sends the YouTube link to Gemini, and Gemini reads only 0:00–10:00 itself (set in `clip.json`).
- **Whisper: yes, an audio file is needed.** Whisper can't read YouTube links. Upload the lesson's audio and
  the code cuts 0:00–10:00 automatically, so you can upload the full lesson. Use a copy you're allowed to download,
  e.g. the MP3 the sheikh's site or channel provides. Downloading from YouTube itself goes against YouTube's terms.

## Then

**Runtime → Run all**, and follow the prompts (upload buttons). At the end, download `qabas_eval_results.zip`
and send it back.
""")

md("## 1. Install packages")
code(r"""
# google-genai: Gemini API client | jiwer: WER/CER | faster-whisper: Whisper on GPU | pandas: results table
!pip -q install -U google-genai jiwer faster-whisper pandas
print("Packages installed")
""")

md("## 2. Load the API key from Colab Secrets")
code(r"""
import os                                              # environment variables
from google.colab import userdata                      # Colab's Secrets panel

try:
    os.environ["GEMINI_API_KEY"] = userdata.get("GEMINI_API_KEY")   # read the secret
    print("Gemini key loaded ✔")
except Exception as e:                                   # secret missing or access not granted
    print("Could not read GEMINI_API_KEY. Add it in the Secrets panel (key icon) and enable Notebook access.")
    raise
""")

md("## 3. Upload the clip files (`clip01.zip`)")
code(r"""
import zipfile, pathlib                                # unzip + paths
from google.colab import files                         # upload widget

clip_dir = pathlib.Path("clip01")                       # expected folder
if not (clip_dir / "reference.txt").exists():           # not uploaded yet
    print("Choose clip01.zip …")
    uploaded = files.upload()                            # opens the file picker
    for name in uploaded:                                # unzip whatever was uploaded
        if name.endswith(".zip"):
            zipfile.ZipFile(name).extractall(".")
for f in ["reference.txt", "terms.txt", "glossary.txt", "clip.json"]:   # check all four exist
    assert (clip_dir / f).exists(), f"Missing clip01/{f}"
print("Clip files ready ✔")
""")

md("## 4. Scoring code (normalization, WER/CER, terms)")
code(CORE)

md("## 5. Load the clip")
code(r"""
import json                                             # read clip.json

clip = json.load(open(clip_dir / "clip.json", encoding="utf-8"))          # link, times, book, sheikh
REFERENCE = open(clip_dir / "reference.txt", encoding="utf-8").read()      # your transcript
TERMS = load_terms(clip_dir / "terms.txt")                                 # names and terms to score
GLOSSARY = open(clip_dir / "glossary.txt", encoding="utf-8").read()        # context for the model

RESULTS = {}                                            # system name -> transcript text
OUT = pathlib.Path("outputs"); OUT.mkdir(exist_ok=True) # where transcripts are saved

print(clip["youtube_url"], f'{clip["start_sec"]}s → {clip["end_sec"]}s')
print("Reference words:", len(REFERENCE.split()), "| Terms:", len(TERMS))
""")

md("""
## 6. Gemini setup

`MODEL` is the Gemini model to test. Google renames models over time: the cell prints the ones your key can use.
To also compare the stronger model, set `MODEL` to a Pro model from the printed list later and re-run sections 7–8.
""")
code(r"""
import time                                             # waits between retries
from google import genai                                # Gemini SDK
from google.genai import types                          # request types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])   # authenticated client
MODEL = "gemini-3.8-flash"                              # model under test (2.5 models are retired for new keys)

names = [m.name.split("/")[-1] for m in client.models.list() if "gemini" in m.name]   # available models
print("Available:", ", ".join(sorted(names)))
assert MODEL in names, f"{MODEL} is not available to this key; pick one from the list above"


def transcribe_gemini(prompt: str, attempts: int = 3) -> str:
    # The video itself: YouTube link + clip window. Gemini fetches it; nothing is downloaded here.
    video = types.Part(
        file_data=types.FileData(file_uri=clip["youtube_url"]),
        video_metadata=types.VideoMetadata(start_offset=f'{clip["start_sec"]}s',
                                           end_offset=f'{clip["end_sec"]}s'),
    )
    cfg = dict(temperature=0,                                           # repeatable output
               max_output_tokens=16384,                                 # room for ~10 minutes of speech
               media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW)  # audio matters, not pixels
    cfg["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)  # no tools used; silences the AFC warning
    if MODEL.startswith("gemini-2.5-flash"):
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)     # only 2.5 Flash accepts a zero budget
    for i in range(attempts):                                          # retry on rate limits / busy server
        try:
            r = client.models.generate_content(
                model=MODEL,
                contents=types.Content(parts=[video, types.Part(text=prompt)]),
                config=types.GenerateContentConfig(**cfg),
            )
            u = r.usage_metadata                                        # token usage (cost indicator)
            print(f"tokens in={u.prompt_token_count} out={u.candidates_token_count}")
            return r.text or ""
        except Exception as e:
            print(f"attempt {i + 1} failed: {e}")
            time.sleep(20 * (i + 1))                                    # back off, then retry
    raise RuntimeError("Gemini failed 3 times")
""")

md("""
## 7. Prompts

Both prompts share the same rules; the context prompt only **adds** the book, sheikh and glossary,
so the difference in scores comes from the context alone.
""")
code(r"""
RULES = '''فرّغ الكلام في هذا المقطع تفريغًا حرفيًا باللغة العربية كما نُطق تمامًا، من بدايته إلى نهايته.
- اكتب كل ما قيل دون تلخيص أو حذف أو إعادة صياغة، بما في ذلك التكرار وتصحيح المتكلم لنفسه.
- لا تُكمل آية أو حديثًا من حفظك؛ اكتب ما نُطق فقط.
- اكتب النص فقط، دون توقيت أو عناوين أو أسماء متحدثين أو تعليقات.
- لا تضع التشكيل.'''

PROMPT_PLAIN = RULES                                     # system 1: rules only

PROMPT_CONTEXT = RULES + f'''

معلومات تساعدك على كتابة الأسماء والمصطلحات بإملائها الصحيح:
- الكتاب: {clip["book"]}
- الشيخ: {clip["sheikh"]}
- الموضوع: {clip.get("topic", "")}
- الأعلام والكتب والمصطلحات التي قد ترد في الدرس:
{GLOSSARY}

استخدم هذه القائمة لكتابة الأسماء والمصطلحات صحيحة إذا نُطقت فقط، ولا تُضف منها شيئًا لم يُقل.'''   # system 2

print(len(PROMPT_PLAIN), "chars plain |", len(PROMPT_CONTEXT), "chars with context")
""")

md("## 8. Run Gemini (plain, then with context)")
code(r"""
for name, prompt in [(f"Gemini plain ({MODEL})", PROMPT_PLAIN),
                     (f"Gemini + context ({MODEL})", PROMPT_CONTEXT)]:
    print("▶", name)
    text = transcribe_gemini(prompt)                     # transcribe the clip
    RESULTS[name] = text                                 # keep for the table
    (OUT / (name.replace(" ", "_").replace("/", "-") + ".txt")).write_text(text, encoding="utf-8")  # save
    s = score_all(REFERENCE, text, TERMS)                # quick look
    print(f'  WER {s["WER"]:.1%} | CER {s["CER"]:.1%} | terms {s["terms_unique"]}\n')
""")

md("""
## 9. Whisper (optional — needs GPU runtime + an audio file)

Skip sections 9–10 if you only want Gemini results. Upload the lesson audio (mp3/m4a/wav/mp4, any length):
the code keeps only the clip window from `clip.json`.
""")
code(r"""
import subprocess                                        # runs ffmpeg

RUN_WHISPER = True                                       # set False to skip Whisper
if RUN_WHISPER:
    print("Choose the lesson audio file …")
    up = files.upload()                                   # file picker
    src = next(iter(up))                                  # uploaded file name
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                    "-ss", str(clip["start_sec"]), "-to", str(clip["end_sec"]),   # keep 0:00–10:00
                    "-ac", "1", "-ar", "16000", "clip_audio.wav"], check=True)    # mono, 16 kHz
    print("Cut to clip_audio.wav ✔")
""")

md("## 10. Run Whisper large-v3 (plain, then with names as prompt)")
code(r"""
if RUN_WHISPER:
    import torch                                         # check for a GPU
    from faster_whisper import WhisperModel              # fast Whisper implementation
    assert torch.cuda.is_available(), "No GPU: Runtime → Change runtime type → T4 GPU, then re-run"
    wmodel = WhisperModel("large-v3", device="cuda", compute_type="float16")   # ~3 GB download first time

    # Whisper's prompt is short (~224 tokens): give it the names and books only
    names_prompt = "، ".join(TERMS[:20])

    for name, prompt in [("Whisper large-v3", None), ("Whisper large-v3 + names", names_prompt)]:
        print("▶", name)
        segments, info = wmodel.transcribe(
            "clip_audio.wav", language="ar", beam_size=5,
            vad_filter=True,                             # skip silences (reduces invented text)
            condition_on_previous_text=False,            # avoids repetition loops
            initial_prompt=prompt,
        )
        text = " ".join(s.text.strip() for s in segments)   # join all segments
        RESULTS[name] = text
        (OUT / (name.replace(" ", "_") + ".txt")).write_text(text, encoding="utf-8")
        s = score_all(REFERENCE, text, TERMS)
        print(f'  WER {s["WER"]:.1%} | CER {s["CER"]:.1%} | terms {s["terms_unique"]}\n')
""")

md("## 11. Results table")
code(r"""
import pandas as pd                                      # table

rows = []
for name, text in RESULTS.items():                       # score every system
    s = score_all(REFERENCE, text, TERMS)
    rows.append({"System": name,
                 "WER": f'{s["WER"]:.1%}', "CER": f'{s["CER"]:.1%}',
                 "Terms (unique)": f'{s["terms_unique"]} ({s["terms_unique_pct"]:.0%})',
                 "Terms (occurrences)": f'{s["terms_occ_pct"]:.0%}',
                 "Words out": len(normalize(text).split())})   # vs reference length, spots dropped text
table = pd.DataFrame(rows)
table.to_csv(OUT / "results.csv", index=False, encoding="utf-8-sig")
print("Reference words:", len(normalize(REFERENCE).split()))
table
""")

md("## 12. What went wrong (missed terms and most common word swaps)")
code(r"""
for name, text in RESULTS.items():
    s = score_all(REFERENCE, text, TERMS)
    lines = [f"=== {name} ===",
             "Missed terms (found/expected): " + (", ".join(s["missed_terms"]) or "none"),
             "Top word swaps (reference → model):"]
    lines += [f"  {r} → {h}  ×{c}" for (r, h), c in top_substitutions(REFERENCE, text, 20)]
    report = "\n".join(lines)
    print(report + "\n")
    (OUT / (name.replace(" ", "_").replace("/", "-") + "_errors.txt")).write_text(report, encoding="utf-8")
""")

md("## 13. Download everything")
code(r"""
import shutil                                            # zip the outputs folder
shutil.make_archive("qabas_eval_results", "zip", OUT)   # transcripts + results.csv + error reports
files.download("qabas_eval_results.zip")                # browser download
""")

md("""
## Send back

Send **`qabas_eval_results.zip`** (or paste the table from section 11 and the error report from section 12).

**Read the "+ context" row with care:** the glossary was written from this same clip, so it knows exactly which
names occur. That makes the context gain look better than it would on a new lesson. For the next clips,
build the glossary *before* listening, from the book and the sheikh's usual references, so the numbers are fair.
""")

nb = new_notebook(cells=cells, metadata={
    "colab": {"provenance": []},
    "kernelspec": {"name": "python3", "display_name": "Python 3"},
    "accelerator": "GPU",
})
nbformat.write(nb, "qabas_transcription_eval.ipynb")
print("notebook written with", len(cells), "cells")

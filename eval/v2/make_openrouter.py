"""Builds qabas_eval_openrouter.ipynb: the v2 transcription notebook, with Gemini called through OpenRouter."""
import nbformat

nb = nbformat.read("qabas_eval_v2.ipynb", 4)
cells = nb.cells


def find(prefix):
    # index of the cell whose source starts with this text
    hits = [i for i, c in enumerate(cells) if c.source.lstrip().startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return hits[0]


# ---------- title and steps ----------
cells[0].source = r"""
# Qabas — transcription evaluation through **OpenRouter**

Same test as the v2 notebook (same 6 lessons, same prompts, same scoring), but every Gemini request goes through
**OpenRouter** instead of Google directly. The question: does it work, and is the quality the same?

| Clip | Sheikh | Lesson |
|---|---|---|
| K1–K3 | Abdulkarim Al-Khudair | شرح متن الورقات في أصول الفقه (02, 03, 04) |
| B1–B3 | Abdulaziz Ibn Baz | شرح المنتقى (كتاب الصلاة), كتاب التوحيد, شرح المنتقى (أول الكتاب) |

**Earlier results with Google directly (3.8 Flash), to compare with:** WER plain / with context:
B1 6.0% / 5.1% · B2 4.4% / 3.6% · B3 15.0% / 15.1%. (The Al-Khudair clips were only run on Flash-Lite: 6.6–9.8%.)

**Metrics** (after removing harakat and unifying letters): **WER** word error rate, **CER** letter error rate,
**Terms** (names/books/terms written correctly), **Negation errors** (a negation word differs from the official transcript).

**Cost:** OpenRouter bills the same per-token prices as Google plus a 5.5% fee on each top-up.
This run is about 12 audio requests of 10 minutes each plus a few small text requests: expect **well under $1**.
The notebook prints what each request cost and the running total.

## Steps

1. On openrouter.ai: add credit (about $2 is plenty), then **Keys → Create key**.
2. In Colab: key icon (Secrets) → Add new secret → name **`OPENROUTER_API_KEY`** → paste the key → turn on **Notebook access**.
   Never paste the key into a cell.
3. **Runtime → Run all.** Nothing to upload.
4. Section 5 runs a tiny test request first. If it stops there, the message says why (no credit, model name, privacy setting).
5. At the end **`qabas_eval_openrouter_results.zip`** downloads. Send it back.
"""

# ---------- install ----------
cells[find("# google-genai: Gemini")].source = r"""
# requests: talk to OpenRouter | jiwer: WER/CER | beautifulsoup4: read the lesson pages | pandas: tables
!pip -q install -U requests jiwer pandas beautifulsoup4
!ffmpeg -version | head -n 1
"""

# ---------- key ----------
cells[find("import os                                              # environment v")].source = r"""
import os                                              # environment variables
from google.colab import userdata                      # Colab's Secrets panel

try:
    os.environ["OPENROUTER_API_KEY"] = userdata.get("OPENROUTER_API_KEY")   # read the secret
    print("OpenRouter key loaded ✔")
except Exception:
    print("Could not read OPENROUTER_API_KEY. Add it in the Secrets panel (key icon) and enable Notebook access.")
    raise
"""

# ---------- Drive note ----------
i = find("## 4b.")
cells[i].source = r"""
## 4b. Save results to Google Drive

Keeps every finished transcript in your Drive (folder `qabas_eval_openrouter`), so nothing is paid for twice:
finished transcripts are skipped when you run the notebook again.
"""

# ---------- client ----------
cells[find("## 5. Gemini setup")].source = r"""
## 5. OpenRouter setup

- The 10-minute clip (about 2.4 MB) is sent inside the request (base64): OpenRouter does not accept audio links.
- The functions keep the same names as the Google notebook (`ask_gemini`, `ask_text`), so sections 6–12 are unchanged.
- Each answer's cost and the provider that served it are recorded in `requests_log.csv`.
- A tiny test request runs first (about $0.001).
"""
cells[find("import re, time                                         # parse wait t")].source = r"""
import re, time, base64, csv                            # waits, audio encoding, request log
import requests                                         # plain HTTP calls to OpenRouter

API = "https://openrouter.ai/api/v1"
HEAD = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "HTTP-Referer": "https://github.com/qabas", "X-Title": "Qabas eval"}   # optional: names the app on OpenRouter

# ---- pick the models from OpenRouter's list ----
catalog = requests.get(f"{API}/models", timeout=60).json()["data"]
ids = {m["id"]: m for m in catalog if m["id"].startswith("google/gemini")}
print("Gemini models on OpenRouter:", ", ".join(sorted(ids)))
MODEL = "google/gemini-3.8-flash"                       # model under test (same as the Google-direct run)
if MODEL not in ids:                                     # fall back to the closest name, e.g. a dated version
    MODEL = next((i for i in sorted(ids, reverse=True) if "gemini-3.8-flash" in i and "lite" not in i), MODEL)
assert MODEL in ids, f"{MODEL} is not on OpenRouter; set MODEL to one of the names above"
# glossaries are plain text work: use the newest stable Flash-Lite (cheaper)
GLOSS_MODEL = next((i for i in sorted(ids, reverse=True) if "flash-lite" in i and "preview" not in i), MODEL)
mods = ids[MODEL].get("architecture", {}).get("input_modalities", [])
print("Transcription model:", MODEL, "| accepts:", mods, "| glossary model:", GLOSS_MODEL)
if mods and "audio" not in mods:
    print("⚠ OpenRouter does not list audio input for this model: the test request below will tell for sure")

LOG = []                                                 # one row per request: model, provider, tokens, cost


class DailyQuotaError(RuntimeError):                     # kept for compatibility with the other sections
    pass


def _gemini_schema(s):
    # Google-style schema ("OBJECT", "STRING"…) → standard JSON Schema ("object", "string"…)
    if isinstance(s, dict):
        return {k: (v.lower() if k == "type" else _gemini_schema(v)) for k, v in s.items()}
    if isinstance(s, list):
        return [_gemini_schema(x) for x in s]
    return s


def _json_format(schema):
    # OpenRouter wants an object at the top: wrap lists as {"items": [...]}
    js = _gemini_schema(schema)
    wrapped = js.get("type") == "array"
    if wrapped:
        js = {"type": "object", "properties": {"items": js}, "required": ["items"]}
    if js.get("type") == "object":
        js.setdefault("additionalProperties", False)
    return {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": js}}, wrapped


def _extract_json(text):
    # tolerate ```json fences or text around the JSON
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    return m.group(0) if m else text


def _call(model, content, max_tokens, temperature=0, schema=None, attempts=5):
    # one request with retries for busy/limit errors; returns the answer text
    body = {"model": model, "messages": [{"role": "user", "content": content}],
            "temperature": temperature, "max_tokens": max_tokens, "usage": {"include": True}}
    wrapped = False
    if schema:
        body["response_format"], wrapped = _json_format(schema)
    for i in range(attempts):
        try:
            r = requests.post(f"{API}/chat/completions", headers=HEAD, json=body, timeout=600)
        except requests.RequestException as e:            # network hiccup or timeout
            wait = 20 * (i + 1); print(f"   retry {i+1} in {wait}s: {e!r}"[:160]); time.sleep(wait); continue
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"error": {"message": r.text[:300]}}
        err = data.get("error") or (data.get("choices") or [{}])[0].get("error")
        if r.status_code == 402:
            raise RuntimeError("OpenRouter says there is not enough credit. Add credit on openrouter.ai and run the cell again.")
        if r.status_code in (401, 403):
            raise RuntimeError(f"OpenRouter refused the key ({r.status_code}): {err}")
        if r.status_code == 404 and "data policy" in str(err).lower():
            raise RuntimeError("OpenRouter found no provider allowed by your privacy settings. "
                               "openrouter.ai → Settings → Privacy: allow paid providers, then run again.")
        if r.status_code == 400 and "response_format" in body:
            # this provider refused the JSON-schema option: ask for JSON in words instead and parse the reply
            print("   note: structured output refused, asking for plain JSON instead")
            body.pop("response_format")
            hint = "\n\nأجب بـ JSON فقط بهذه البنية: " + json.dumps(_gemini_schema(schema), ensure_ascii=False)
            msg = body["messages"][0]
            if isinstance(msg["content"], list):
                msg["content"][-1]["text"] += hint
            else:
                msg["content"] += hint
            continue
        if err or r.status_code != 200:
            wait = 20 * (i + 1)
            print(f"   retry {i+1} in {wait}s: HTTP {r.status_code} {str(err)[:140]}")
            time.sleep(wait); continue
        ch, usage = data["choices"][0], data.get("usage", {})
        LOG.append({"model": model, "provider": data.get("provider", "?"), "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"), "cost_usd": usage.get("cost"),
                    "finish": ch.get("finish_reason")})
        if ch.get("finish_reason") == "length":
            print("   ⚠ output was cut off (max_tokens)")
        text = ch["message"].get("content") or ""
        if schema:                                        # return plain JSON text, like the Google notebook
            obj = json.loads(_extract_json(text))
            if wrapped and isinstance(obj, dict):
                obj = obj.get("items", [])
            text = json.dumps(obj, ensure_ascii=False)
        return text
    raise RuntimeError(f"OpenRouter failed {attempts} times on {model}")


def ask_gemini(audio_path, prompt, schema=None, temperature=0):
    # send an audio file + prompt, return the text answer
    b64 = base64.b64encode(pathlib.Path(audio_path).read_bytes()).decode()
    content = [{"type": "input_audio", "input_audio": {"data": b64, "format": "mp3"}},
               {"type": "text", "text": prompt}]
    return _call(MODEL, content, max_tokens=24000, temperature=temperature, schema=schema)


def ask_text(prompt, schema=None, model=None):
    # text-only request (used to build glossaries)
    return _call(model or GLOSS_MODEL, prompt, max_tokens=4096, schema=schema)


def spent():
    # total cost so far, and save the request log
    with open(OUT / "requests_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["model", "provider", "prompt_tokens", "completion_tokens", "cost_usd", "finish"])
        w.writeheader(); w.writerows(LOG)
    return sum(x["cost_usd"] or 0 for x in LOG)


# ---- tiny test: 5 seconds of the first clip + a JSON answer ----
test = OUT / "test5s.mp3"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-t", "5", "-i", str(OUT / READY[0]["id"] / "clip.mp3"), str(test)], check=True)
ans = ask_gemini(test, "ما أول كلمة تسمعها؟ أجب في الحقل word.",
                 schema={"type": "OBJECT", "properties": {"word": {"type": "STRING"}}, "required": ["word"]})
print("Test answer:", ans, "| provider:", LOG[-1]["provider"], f"| cost ${LOG[-1]['cost_usd'] or 0:.5f}")
print("Audio + JSON through OpenRouter work ✔")
"""

# ---------- print cost after the heavy sections ----------
for prefix in ["def transcribe_to(c, prompt, f):", "WINDOW = 45"]:
    cells[find(prefix)].source += '\nprint(f"Spent so far: ${spent():.3f}")\n'

# ---------- glossary passes (C/D) are optional here, to keep the cost down ----------
i = find('for c in READY:\n    d = OUT / c["id"]\n    jobs = [("C"')
cells[i].source = 'RUN_GLOSSARY_PASSES = False     # True = also run C and D (about 9 more audio requests)\n' \
    'if not RUN_GLOSSARY_PASSES:\n    print("Skipped (set RUN_GLOSSARY_PASSES = True to run C and D)")\n' \
    'for c in (READY if RUN_GLOSSARY_PASSES else []):\n' + cells[i].source.split("for c in READY:\n", 1)[1]
cells[i - 1].source = "## 9. Transcribe with the glossaries (optional here: off by default)"

# ---------- comparison with Google direct ----------
i = find("import pandas as pd\n\nSYSTEMS")
cells[i].source += r'''

# ---- same clips, Google directly (earlier 3.8 Flash run) vs OpenRouter ----
GOOGLE = {("B1", "A plain"): 0.060, ("B1", "B context"): 0.051, ("B2", "A plain"): 0.044,
          ("B2", "B context"): 0.036, ("B3", "A plain"): 0.150, ("B3", "B context"): 0.151}
cmp = final[final.System.isin(["A plain", "B context"])][["Clip", "System", "WER", "Negation errors", "Flag"]].copy()
cmp["WER Google direct"] = [GOOGLE.get((c, s)) for c, s in zip(cmp.Clip, cmp.System)]
cmp["Difference"] = cmp.WER - cmp["WER Google direct"]
cmp.to_csv(OUT / "compare_google.csv", index=False, encoding="utf-8-sig")
print("OpenRouter vs Google direct (same model, same clips):")
display(cmp.style.format({"WER": "{:.1%}", "WER Google direct": "{:.1%}", "Difference": "{:+.1%}"}, na_rep="-"))
print(f"Total spent on OpenRouter: ${spent():.3f} over {len(LOG)} requests | providers used:",
      ", ".join(sorted({x['provider'] for x in LOG})))
'''

# ---------- names of folder and zip ----------
for c in cells:
    c.source = (c.source.replace("qabas_eval_v2_results", "qabas_eval_openrouter_results")
                .replace("qabas_eval_v2", "qabas_eval_openrouter"))

nbformat.write(nb, "qabas_eval_openrouter.ipynb")
print("written:", len(cells), "cells")

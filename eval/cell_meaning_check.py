# ===== 12. Meaning check: find and fix dropped/added negations =====
import json                                              # read the model's verdict
import jiwer                                             # word alignment

BASE_NAME  = f"Gemini plain ({MODEL})"                   # version to fix
OTHER_NAME = f"Gemini + context ({MODEL})"               # second version to compare against
WINDOW = 45                                              # seconds of audio around each spot, each side

# Words whose presence or absence flips the meaning (normalized spelling)
NEGATIONS = {"لا", "لم", "لن", "ما", "ليس", "ليست", "لست", "غير", "الا", "بلا", "دون"}

def is_negation(w):
    """Negation word, also with a و / ف prefix (ولا، فلم، وما)."""
    return w in NEGATIONS or (len(w) > 2 and w[0] in "وف" and w[1:] in NEGATIONS)

def find_risks(a_text, b_text, ctx=8):
    """Spots where A and B differ and a negation is involved in the difference."""
    A, B = normalize(a_text).split(), normalize(b_text).split()
    chunks = [c for c in jiwer.process_words(" ".join(A), " ".join(B)).alignments[0]]
    groups, cur = [], []                                 # merge back-to-back differences into one spot
    for c in chunks:
        if c.type == "equal":
            if cur: groups.append(cur); cur = []
        else:
            cur.append(c)
    if cur: groups.append(cur)
    risks = []
    for g in groups:
        a0, a1 = g[0].ref_start_idx, g[-1].ref_end_idx   # span in A
        b0, b1 = g[0].hyp_start_idx, g[-1].hyp_end_idx   # span in B
        if not any(is_negation(w) for w in A[a0:a1] + B[b0:b1]):
            continue                                     # difference doesn't touch a negation
        risks.append({"id": len(risks) + 1, "a_idx": (a0, a1), "b_words": B[b0:b1],
                      "before": " ".join(A[max(0, a0 - ctx):a0]),
                      "A": " ".join(A[a0:a1]) or "(لا شيء)",
                      "B": " ".join(B[b0:b1]) or "(لا شيء)",
                      "after": " ".join(A[a1:a1 + ctx]),
                      "pos": (a0 + a1) / 2 / max(len(A), 1)})   # rough position in the clip (0..1)
    return risks

CHECK_PROMPT = '''استمع إلى هذا الجزء من الدرس. اختلفت نسختان من التفريغ في الموضع التالي، والاختلاف يتعلق بأداة نفي قد تقلب المعنى:

...{before} [النسخة A: {A}] [النسخة B: {B}] {after}...

ابحث عن هذه الجملة في الصوت واستمع إليها بدقة، وانتبه لوجود أداة النفي أو غيابها.
- إن طابقت النسخة A ما قيل فعلًا فأجب choice = "A"
- إن طابقت النسخة B فأجب choice = "B"
- إن لم تطابق أيّ منهما فأجب choice = "other" واكتب في heard الكلمات التي قيلت مكان الموضع المختلف فقط.'''

VERDICT_SCHEMA = {"type": "OBJECT",
                  "properties": {"choice": {"type": "STRING", "enum": ["A", "B", "other"]},
                                 "heard": {"type": "STRING"}},
                  "required": ["choice", "heard"]}

def check_spot(r):
    """Send only the audio around the spot and ask which version was actually said."""
    dur = clip["end_sec"] - clip["start_sec"]
    t = clip["start_sec"] + r["pos"] * dur               # estimated time of the spot
    s = max(clip["start_sec"], int(t - WINDOW))
    e = min(clip["end_sec"], int(t + WINDOW))
    video = types.Part(file_data=types.FileData(file_uri=clip["youtube_url"]),
                       video_metadata=types.VideoMetadata(start_offset=f"{s}s", end_offset=f"{e}s"))
    cfg = types.GenerateContentConfig(
        temperature=0, media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        response_mime_type="application/json", response_schema=VERDICT_SCHEMA,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    prompt = CHECK_PROMPT.format(**r)
    for i in range(3):
        try:
            resp = client.models.generate_content(model=MODEL, config=cfg,
                       contents=types.Content(parts=[video, types.Part(text=prompt)]))
            v = json.loads(resp.text); v["window"] = f"{s//60}:{s%60:02d}–{e//60}:{e%60:02d}"
            return v
        except Exception as ex:
            print("  retry:", ex); time.sleep(15 * (i + 1))
    return {"choice": "unsure", "heard": "", "window": f"{s}s–{e}s"}

def apply_verdicts(a_text, risks, verdicts):
    """Patch A from the end backwards so earlier indexes stay valid."""
    A = normalize(a_text).split()
    for r in sorted(risks, key=lambda r: r["a_idx"][0], reverse=True):
        v = verdicts[r["id"]]
        if v["choice"] == "B":
            new = r["b_words"]
        elif v["choice"] == "other":
            new = normalize(v["heard"]).split()
        else:
            continue                                     # A confirmed, or unsure: leave as is (flagged)
        A[r["a_idx"][0]:r["a_idx"][1]] = new
    return " ".join(A)

# --- run it ---
base, other = RESULTS[BASE_NAME], RESULTS[OTHER_NAME]
risks = find_risks(base, other)
print(f"{len(risks)} negation disagreement(s) found\n")

verdicts, lines = {}, []
for r in risks:
    v = check_spot(r)
    verdicts[r["id"]] = v
    line = (f'{r["id"]}) [{v["window"]}] ...{r["before"]} [A: {r["A"]}] [B: {r["B"]}] {r["after"]}...\n'
            f'   → verdict: {v["choice"]}' + (f' | heard: {v["heard"]}' if v["choice"] == "other" else ""))
    print(line + "\n"); lines.append(line)

fixed = apply_verdicts(base, risks, verdicts)
name = BASE_NAME + " + meaning check"
RESULTS[name] = fixed
(OUT / (name.replace(" ", "_").replace("/", "-") + ".txt")).write_text(fixed, encoding="utf-8")
(OUT / "meaning_check_report.txt").write_text("\n\n".join(lines) or "no disagreements", encoding="utf-8")

for n in (BASE_NAME, name):
    s = score_all(REFERENCE, RESULTS[n], TERMS)
    print(f'{n}: WER {s["WER"]:.1%} | CER {s["CER"]:.1%}')
print("\n«لا يتصور في الشرط» present in fixed text:", "لا يتصور في الشرط" in fixed)

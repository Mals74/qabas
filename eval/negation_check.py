# ---- Meaning check: catch dropped/added negations by comparing two transcripts ----
import json                                              # parse the model's answer
import jiwer                                             # word alignment between the two versions

# Words whose presence or absence flips the meaning (normalized spelling, see normalize())
NEGATIONS = {"لا", "لم", "لن", "ما", "ليس", "ليست", "غير", "الا", "بلا", "دون"}


def _is_negation(word: str) -> bool:
    """True for a negation word, also with a و / ف prefix (ولا، فلم، وما …)."""
    return word in NEGATIONS or (len(word) > 2 and word[0] in "وف" and word[1:] in NEGATIONS)


def find_meaning_risks(a_text: str, b_text: str, ctx: int = 7) -> list:
    """Spots where version A and version B differ AND a negation word is involved."""
    A, B = normalize(a_text).split(), normalize(b_text).split()        # normalized word lists
    out = jiwer.process_words(" ".join(A), " ".join(B))                # align A against B
    risks = []                                                         # collected risky spots
    for chunk in out.alignments[0]:                                    # each aligned block
        if chunk.type == "equal":                                      # identical text: nothing to check
            continue
        a_span = A[chunk.ref_start_idx:chunk.ref_end_idx]             # A's words here
        b_span = B[chunk.hyp_start_idx:chunk.hyp_end_idx]             # B's words here
        if not any(_is_negation(w) for w in a_span + b_span):         # only meaning-flipping differences
            continue
        risks.append({
            "id": len(risks) + 1,
            "before": " ".join(A[max(0, chunk.ref_start_idx - ctx):chunk.ref_start_idx]),  # context before
            "A": " ".join(a_span) or "(لا شيء)",                       # version A (empty = word missing)
            "B": " ".join(b_span) or "(لا شيء)",                       # version B
            "after": " ".join(A[chunk.ref_end_idx:chunk.ref_end_idx + ctx]),               # context after
            "a_idx": (chunk.ref_start_idx, chunk.ref_end_idx),         # where to patch A
            "b_words": b_span,                                         # replacement if B wins
        })
    return risks


ARBITER_PROMPT = """استمع إلى هذا المقطع من الدرس. فيما يلي مواضع اختلفت فيها نسختان من التفريغ، وكل اختلاف يتعلق بأداة نفي أو استثناء قد تقلب المعنى.
لكل موضع: الكلام قبله، ثم النسخة (A) والنسخة (B)، ثم الكلام بعده.
استمع إلى الموضع وحدّد أي النسختين تطابق ما قاله المتكلم فعلًا، وانتبه خاصة لوجود أداة النفي أو غيابها.
إن لم تطابق أي منهما فاختر other واكتب في heard ما سمعته بالضبط.

{items}
"""


def arbitrate(risks: list, ask_model) -> list:
    """Ask the model to listen again and pick the right version for each risky spot.

    ask_model(prompt) must return JSON text: [{"id": 1, "choice": "A"|"B"|"other", "heard": "..."}]
    """
    if not risks:                                                      # nothing to check
        return []
    items = "\n".join(f'{r["id"]}) ...{r["before"]} [A: {r["A"]}] [B: {r["B"]}] {r["after"]}...' for r in risks)
    answer = json.loads(ask_model(ARBITER_PROMPT.format(items=items))) # model's verdicts
    return answer


def apply_verdicts(a_text: str, risks: list, verdicts: list) -> str:
    """Patch version A with the verdicts (right to left so indexes stay valid)."""
    A = normalize(a_text).split()                                      # A as a word list
    by_id = {v["id"]: v for v in verdicts}                             # verdict per spot
    for r in sorted(risks, key=lambda r: r["a_idx"][0], reverse=True): # patch from the end backwards
        v = by_id.get(r["id"])
        if not v or v.get("choice") == "A":                            # A confirmed: keep it
            continue
        new = r["b_words"] if v["choice"] == "B" else normalize(v.get("heard", "")).split()
        s, e = r["a_idx"]
        A[s:e] = new                                                   # replace the disputed words
    return " ".join(A)

"""Measures the app's hadith search on the 111-question test set (run from the backend folder).

    python ../notebooks/hadith_eval/eval_hadith.py bm25        # search + quote rule only (no AI, no key)
    python ../notebooks/hadith_eval/eval_hadith.py full        # the app's whole pipeline, with the Flash-Lite check

Two answer keys:
  strict      only the exact source hadith counts (Bukhari / Muslim numbers, as in the first evaluation)
  same hadith another narration of the same hadith counts, in any of the nine books: it shares 8 or more consecutive
              words of the text with the source hadith (chain of narrators left out), or, for partial quotes, contains
              the quote at 90% or more
The 6 questions that were "not in the books" with Bukhari + Muslim are scored separately: 5 of them are in the
nine books (their answer key is set below, by a phrase every narration of that hadith contains).
"""
import json
import pathlib
import sys
import time

from rapidfuzz import fuzz

sys.path.insert(0, ".")
from app import hadith, hadith_index                     # noqa: E402
from app.arabic import normalize                         # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
TESTS = json.loads((HERE / "testset.json").read_text(encoding="utf-8"))
TYPES = ["real", "partial", "partial_noisy", "paraphrase", "name", "new_in_books"]   # new = absent from Bukhari/Muslim

# Hadith that were outside Bukhari + Muslim: a phrase that identifies every narration of each (None = not in the books)
NEW_IN_BOOKS = {
    "not_in_corpus-01": "اول ما يحاسب",
    "not_in_corpus-02": "هو الطهور ماوه الحل ميتته",
    "not_in_corpus-03": "نهيت عن قتل المصلين",
    "not_in_corpus-04": "من حسن اسلام المرء تركه ما لا يعنيه",
    "not_in_corpus-05": None,                            # Musnad Ahmad: not in these nine books
    "not_in_corpus-06": "البطاقه",
}

import os                                                # noqa: E402
# HADITH_EVAL_CORPUS=<file> measures another library file (e.g. the old two-book one) with the same scoring
idx = hadith_index.HadithIndex(os.environ["HADITH_EVAL_CORPUS"]) if os.environ.get("HADITH_EVAL_CORPUS") \
    else hadith_index.get_index()
if os.environ.get("HADITH_EVAL_CORPUS"):
    hadith_index.get_index = lambda: idx                  # the app's pipeline uses the same file

# Checked by hand: the automatic test misses these, but they are the same hadith in another narration
MANUAL_SAME = {
    ("real-01", "tirmidhi:214"),       # shorter narration of Muslim 233 (without «ورمضان إلى رمضان»)
    ("paraphrase-05", "nawawi:7"),     # «الدين النصيحة», Muslim 55
    ("partial-01", "muslim:2471"),     # the angels shading Jabir's father at Uhud, Bukhari 4079/4080
    # checked by hand on the full run of 2026-10-03 (see full_results_2026-10-03.txt)
    ("paraphrase-06", "ibnmajah:4013"),       # «من رأى منكم منكرا», Muslim 49
    ("name-07", "tirmidhi:3148"),             # the great intercession (people go to Adam, then Nuh …)
    ("partial-12", "bukhari:6544"),           # «يا أهل الجنة لا موت», Muslim 2850
    ("partial_noisy-07", "ibnmajah:2323"),    # false oath to take a Muslim's property, Bukhari 6659
    ("partial_noisy-16", "bukhari:7558"),     # picture-makers «أحيوا ما خلقتم», Bukhari 5951
    ("partial_noisy-17", "ibnmajah:3232"),    # Abu Tha'laba: every fanged beast, Bukhari 5780
    ("partial_noisy-23", "bukhari:3482"),     # the woman and the cat, Muslim 2242
    ("partial_noisy-24", "malik:1300"),       # selling fruit before it ripens, Bukhari 2198
    ("partial_noisy-27", "bukhari:2016"),     # sujud in water and mud, Bukhari 813
}
_norm = {}


def text_of(g: str) -> str:
    if g not in _norm:
        _norm[g] = normalize(idx.info(g)["text"])
    return _norm[g]


def same_hadith(cand: str, test: dict) -> bool:
    """Is this result an acceptable answer under the 'same hadith' key?"""
    tid = test["id"]
    if tid in NEW_IN_BOOKS:
        phrase = NEW_IN_BOOKS[tid]
        return bool(phrase) and normalize(phrase) in text_of(cand)
    if cand in test["gold"] or (tid, cand) in MANUAL_SAME:
        return True
    c = text_of(cand)
    if test["type"].startswith("partial") and len(c) > 20 and fuzz.partial_ratio(normalize(test["query"]), c) >= 90:
        return True
    grams = _grams(cand)
    if any(grams & _grams(g) for g in test["gold"]):
        return True
    for g in test["gold"]:                                # short narrations: whole-text match
        a, b = sorted((text_of(g), c), key=len)
        if len(a) > 30 and fuzz.partial_ratio(a, b) >= 90:
            return True
    return False


_CHAIN = {"حدثنا", "حدثني", "اخبرنا", "اخبرني", "انبانا", "عن", "سمعت", "حدثه"}
_gram_cache = {}


def _grams(g: str, run: int = 8) -> set:
    """Runs of 8 consecutive words of a hadith's text, leaving out chain-of-narrators runs."""
    if g not in _gram_cache:
        words = hadith_index.prep(idx.info(g)["text"]).split()
        _gram_cache[g] = {" ".join(words[i:i + run]) for i in range(len(words) - run + 1)
                          if not _CHAIN & set(words[i:i + run])}
    return _gram_cache[g]


def strict_hit(cand: str, test: dict) -> bool:
    return cand in test["gold"]


def score(ranked: dict, key) -> dict:
    """R@1, R@5, R@10 and MRR per type, over the questions that have an answer under this key."""
    out = {}
    for typ in TYPES + ["ALL"]:
        tests = [t for t in TESTS if t["gold"] and (typ == "ALL" or t["type"] == typ)
                 and not (key is strict_hit and t["type"] == "new_in_books")]      # strict = the original key
        r1 = r5 = r10 = mrr = 0
        for t in tests:
            hits = [i for i, g in enumerate(ranked[t["id"]][:10]) if key(g, t)]
            first = hits[0] if hits else None
            r1 += first == 0
            r5 += first is not None and first < 5
            r10 += first is not None
            mrr += 1 / (first + 1) if first is not None else 0
        n = max(len(tests), 1)
        out[typ] = {"n": len(tests), "R@1": r1 / n, "R@5": r5 / n, "R@10": r10 / n, "MRR": mrr / n}
    return out


def table(title: str, ranked: dict) -> None:
    print(f"\n{title}")
    print(f"{'type':15} {'n':>4} {'strict R@1':>10} {'R@10':>6} {'MRR':>5}   {'n':>4} {'same-hadith R@1':>15} {'R@10':>6} {'MRR':>5}")
    s, l = score(ranked, strict_hit), score(ranked, same_hadith)
    for typ in TYPES + ["ALL"]:
        a, b = s[typ], l[typ]
        print(f"{typ:15} {a['n']:4d} {a['R@1']:10.0%} {a['R@10']:6.0%} {a['MRR']:5.2f}   "
              f"{b['n']:4d} {b['R@1']:15.0%} {b['R@10']:6.0%} {b['MRR']:5.2f}")


def run_bm25() -> dict:
    ranked, rule = {}, {}
    for t in TESTS:
        c = idx.candidates(t["query"], k=10)
        ranked[t["id"]] = c
        rule[t["id"]] = bool(c) and idx.quote_rule(t["query"], c[0])
    table(f"BM25 over {len(idx.books)} books: {', '.join(idx.books)} (first result = what BM25 ranks first)", ranked)
    pos = [t for t in TESTS if t["gold"]]
    print(f"\nquote rule settled {sum(rule[t['id']] for t in TESTS)} of {len(TESTS)} questions; "
          f"right under 'same hadith' on {sum(rule[t['id']] and same_hadith(ranked[t['id']][0], t) for t in pos)} "
          f"of the {sum(rule[t['id']] for t in pos)} answerable ones it settled")
    new = {tid: ranked[tid] for tid in NEW_IN_BOOKS}
    print("formerly 'not in the books':", {tid: (same_hadith(r[0], {'id': tid, 'gold': []}) if r else False)
                                          for tid, r in new.items()})
    return ranked


def run_full() -> dict:
    """The app's own pipeline (hadith.takhrij_many) with the real provider: rule, then the Flash-Lite check."""
    from app.ai import get_provider
    provider = get_provider()
    print("provider:", getattr(provider, "name", provider))
    results, t0 = {}, time.time()
    for i in range(0, len(TESTS), 8):                     # 8 quotes per call -> 2 check requests per call
        chunk = TESTS[i:i + 8]
        results.update(hadith.takhrij_many([(t["id"], t["query"]) for t in chunk], provider))
        print(f"  {min(i + 8, len(TESTS))}/{len(TESTS)}", flush=True)
    print(f"time: {time.time() - t0:.0f} s")
    bm = {t["id"]: idx.candidates(t["query"], k=10) for t in TESTS}
    ranked, shown = {}, {}
    for t in TESTS:
        r = results[t["id"]]
        top = [x["group"] for x in r["results"]] if r["method"] in ("rule", "check") else []
        ranked[t["id"]] = (top + [g for g in bm[t["id"]] if g not in top])[:10]
        shown[t["id"]] = r
    table("The app's pipeline (rule + Flash-Lite check; first result = what the app shows as confirmed, "
          "else BM25's order)", ranked)
    pos = [t for t in TESTS if t["gold"]]
    conf = lambda t: shown[t["id"]]["method"] in ("rule", "check")                        # noqa: E731
    right = lambda t: conf(t) and same_hadith(shown[t["id"]]["results"][0]["group"], t)   # noqa: E731
    neg = [t for t in TESTS if t["id"] == "not_in_corpus-05"]
    print("\nWhat the user sees (answerable questions, 'same hadith' key):")
    print(f"  confirmed and right            {sum(right(t) for t in pos)} / {len(pos)}")
    print(f"  confirmed but wrong            {sum(conf(t) and not right(t) for t in pos)} / {len(pos)}")
    print(f"  said 'not found' (Dorar link)  {sum(shown[t['id']]['method'] == 'none' for t in pos)} / {len(pos)}")
    print(f"  unconfirmed candidates shown   {sum(shown[t['id']]['method'] == 'candidate' for t in pos)} / {len(pos)}")
    print(f"  by method: " + ", ".join(f"{m}={sum(shown[t['id']]['method'] == m for t in TESTS)}"
                                       for m in ("rule", "check", "candidate", "none")))
    print("  hadith not in the nine books (zamzam): " + ", ".join(
        f"{shown[t['id']]['method']}" + (f" → {shown[t['id']]['results'][0]['source']}" if shown[t['id']]['results'] else "")
        for t in neg))
    for t in pos:
        if conf(t) and not right(t):
            print(f"  ✗ {t['id']}: «{t['query'][:60]}» → {shown[t['id']]['results'][0]['source']}")
    out = HERE / "full_results.json"
    out.write_text(json.dumps(shown, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", out)
    return ranked


if __name__ == "__main__":
    for t in TESTS:                                       # the five that are now in the books become answerable
        if NEW_IN_BOOKS.get(t["id"]):
            t["gold"] = ["(phrase)"]
            t["type"] = "new_in_books"
    mode = sys.argv[1] if len(sys.argv) > 1 else "bm25"
    run_full() if mode == "full" else run_bm25()

"""Builds backend/data/hadith_corpus.json.gz: nine hadith books, in the compact form the app searches.

Run from the backend folder:
    python -m tools.build_hadith_corpus                      # downloads the editions (needs internet)
    python -m tools.build_hadith_corpus --from-dir DIR       # uses DIR/ara-<book>.json files that exist there

Output (gzipped JSON):
  groups:  {group_id: {"ref": "سنن أبي داود (3568)", "grade": "...", "text": <fullest wording, with harakat>}}
  records: [[record_id, group_id, normalized search text], ...]   # what BM25 searches and the quote rule reads
A "group" is one hadith: Muslim repeats a hadith with other chains (8.01, 8.02 …), and they share one group.
"""
import argparse
import gzip
import json
import pathlib

from app.arabic import normalize
from tools.hadith_source import BOOKS, SOURCE_URL, build

OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "hadith_corpus.json.gz"


def load_raw(from_dir: str | None) -> dict:
    raw = {}
    for book in BOOKS:
        if from_dir:
            path = pathlib.Path(from_dir) / f"ara-{book}.json"
            if not path.exists():
                print(f"  (skipped {book}: no {path.name})")
                continue
            raw[book] = json.loads(path.read_text(encoding="utf-8"))
        else:
            import httpx
            print(f"  downloading {book} …", flush=True)
            raw[book] = httpx.get(SOURCE_URL.format(book=book), timeout=180, follow_redirects=True).json()
    return raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dir")
    args = ap.parse_args()
    raw = load_raw(args.from_dir)
    recs = build(raw)
    fullest: dict[str, dict] = {}
    for r in recs:
        g = r["group"]
        if g not in fullest or len(r["matn_norm"]) > len(fullest[g]["matn_norm"]):
            fullest[g] = r
    data = {
        "source": "fawazahmed0/hadith-api (" + ", ".join(f"ara-{b}" for b in raw) + ")",
        "books": list(raw),
        "groups": {g: {"ref": r["ref"], "grade": r["grade"], "text": r["matn"]} for g, r in fullest.items()},
        "records": [[r["id"], r["group"], normalize(r["search_text"])] for r in recs],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    per_book = {b: sum(1 for r in recs if r["book"] == b) for b in raw}
    graded = sum(1 for g, v in data["groups"].items() if v["grade"] and not g.startswith(("bukhari:", "muslim:")))
    print(f"{len(recs)} records, {len(data['groups'])} distinct hadith → {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
    print("per book:", per_book)
    print("hadith outside the two Sahihs with a grade in the data:", graded)


if __name__ == "__main__":
    main()

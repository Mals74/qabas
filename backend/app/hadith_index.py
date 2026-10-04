"""Finding the hadith the sheikh quoted, in nine hadith books (the two Sahihs, the four Sunan, the Muwatta,
the Nawawi Forty and the Qudsi Forty), from fawazahmed0/hadith-api.

Step 1 (here): Haystack BM25 word search over the books -> the 12 most likely distinct hadith.
Step 2 (here): the quote rule. If the top hadith contains 5 or more consecutive words of what the sheikh said,
               it is accepted without any AI call (measured on Bukhari + Muslim: settled 45 of 111 test questions,
               44 right, and accepted none of the 6 hadith that are not in those books).
Step 3 (hadith.py): for the rest, a light Gemini model reads the candidates and picks the right one or says none.

We only ever *display* the text of the books themselves, never text produced by the AI.
"""
import gzip
import json
import re
import threading
from functools import lru_cache

from .arabic import normalize
from .config import HADITH_CANDIDATES, HADITH_CORPUS, HADITH_RULE_WORDS

# Honorific phrases appear in almost every hadith, so they carry no signal for search
_HONORIFIC = re.compile(r"صلي الله عليه وسلم|رضي الله عنهما|رضي الله عنها|رضي الله عنهم|رضي الله عنه|عليه السلام")


def prep(text: str) -> str:
    """Text as BM25 sees it: normalized, honorifics removed."""
    return " ".join(_HONORIFIC.sub(" ", normalize(text)).split())


class HadithIndex:
    """The books, loaded once."""

    def __init__(self, path=HADITH_CORPUS):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        # heavy imports stay here so the app starts fast and mock mode without a corpus still works
        from haystack import Document
        from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
        from haystack.document_stores.in_memory import InMemoryDocumentStore

        self.books: list[str] = data.get("books", ["bukhari", "muslim"])
        self.groups: dict[str, dict] = data["groups"]
        self.versions: dict[str, list[str]] = {}          # every version of a hadith, normalized (for the quote rule)
        docs = []
        for rid, group, norm in data["records"]:
            text = prep(norm)                             # one string, shared by BM25 and the quote rule (memory)
            self.versions.setdefault(group, []).append(text)
            docs.append(Document(id=rid, content=text, meta={"group": group}))
        del data["records"]
        store = InMemoryDocumentStore(bm25_algorithm="BM25Plus")
        store.write_documents(docs)
        self._retriever = InMemoryBM25Retriever(store, top_k=60)

    def candidates(self, query: str, k: int = HADITH_CANDIDATES) -> list[str]:
        """Ranked distinct hadith (group ids) for a quote."""
        q = prep(query)
        if not q:
            return []
        out: list[str] = []
        for d in self._retriever.run(query=q)["documents"]:
            g = d.meta["group"]
            if g not in out:
                out.append(g)
            if len(out) == k:
                break
        return out

    def quote_rule(self, query: str, group: str, run: int = HADITH_RULE_WORDS) -> bool:
        """True when some version of this hadith contains `run` consecutive words of the quote."""
        words = prep(query).split()
        grams = [" ".join(words[i:i + run]) for i in range(len(words) - run + 1)]
        return any(f" {g} " in f" {text} " for g in grams for text in self.versions.get(group, ()))

    def info(self, group: str) -> dict:
        g = self.groups[group]
        return {"group": group, "ref": g["ref"], "grade": g.get("grade", ""), "text": g["text"]}


_lock = threading.Lock()


@lru_cache(maxsize=1)
def _load() -> HadithIndex:
    return HadithIndex(HADITH_CORPUS)


def get_index():
    """The index, or None when the corpus file is missing (then only the Dorar link is offered)."""
    if not HADITH_CORPUS.exists():
        return None
    with _lock:
        return _load()

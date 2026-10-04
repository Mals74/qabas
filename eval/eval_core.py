# ---- Arabic normalization + scoring (same rules as the Qabas backend) ----
import re                                            # regular expressions for text cleanup
from collections import Counter                      # counts substitution pairs for error analysis
import jiwer                                         # standard WER/CER library

# Harakat, Quranic marks, dagger alef, tatweel: removed before comparing
_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]")
_ALEF = re.compile("[آأإٱٲٳ]")   # أ إ آ ٱ -> ا
_NON_LETTERS = re.compile("[^ء-ي0-9\\s]")           # punctuation, brackets, Latin, symbols
_SPACES = re.compile(r"\s+")                                   # runs of whitespace


def normalize(text: str) -> str:
    """Make two Arabic texts comparable: no harakat, unified letters, no punctuation."""
    t = _DIACRITICS.sub("", text or "")              # drop harakat and marks
    t = _ALEF.sub("ا", t)                            # unify alef forms
    t = t.replace("ى", "ي")                          # alef maqsura -> ya
    t = t.replace("ة", "ه")                          # ta marbuta -> ha
    t = t.replace("ؤ", "و").replace("ئ", "ي")        # hamza seats -> plain letters
    t = t.replace("ء", "")                           # standalone hamza is written inconsistently
    t = re.sub(r"ي{2,}", "ي", t)                     # شيئا -> شييا -> شيا
    t = _NON_LETTERS.sub(" ", t)                     # punctuation -> space
    return _SPACES.sub(" ", t).strip()               # single spaces, trimmed


def wer_cer(reference: str, hypothesis: str) -> dict:
    """Word and character error rates after normalization (lower is better)."""
    ref, hyp = normalize(reference), normalize(hypothesis)       # compare normalized forms
    return {
        "WER": jiwer.wer(ref, hyp),                              # word-level error rate
        "CER": jiwer.cer(ref.replace(" ", ""), hyp.replace(" ", "")),  # letter-level, spaces ignored
    }


def _term_pattern(term: str) -> re.Pattern:
    """Regex that finds a term even with attached prefixes: و ف ب ك ل (e.g. وابن، كالبهوتي، للمختصر)."""
    t = normalize(term)                                          # normalized term
    forms = [r"[وفبكل]{0,2}" + re.escape(t)]                     # prefix + term as written
    if t.startswith("ال"):                                        # ل + ال merges into لل
        forms.append(r"[وف]?لل" + re.escape(t[2:]))               # e.g. للمختصر
    return re.compile(r"(?<!\S)(?:" + "|".join(forms) + r")(?!\S)")  # whole-word match


def load_terms(path: str) -> list:
    """One term per line; lines starting with # are comments; text after | is ignored here."""
    terms = []                                                   # collected terms
    for line in open(path, encoding="utf-8"):                    # read each line
        line = line.split("|")[0].strip()                        # drop optional variants after |
        if line and not line.startswith("#"):                    # skip blanks and comments
            terms.append(line)                                   # keep the term
    return terms


def term_scores(reference: str, hypothesis: str, terms: list) -> dict:
    """How many names/terms came out right.

    unique      = share of different terms (present in the reference) found at least once
    occurrences = share of all term occurrences reproduced (min(ref, hyp) per term)
    """
    ref, hyp = normalize(reference), normalize(hypothesis)       # normalized texts
    found_unique, total_unique, got_occ, total_occ = 0, 0, 0, 0  # counters
    missed = []                                                  # terms the model got wrong
    for term in terms:                                           # check each term
        pat = _term_pattern(term)                                # prefix-aware pattern
        r = len(pat.findall(ref))                                # times in the reference
        if r == 0:                                               # not in this clip -> not scored
            continue
        h = len(pat.findall(hyp))                                # times in the model output
        total_unique += 1                                        # one more scorable term
        total_occ += r                                           # all its occurrences
        got_occ += min(r, h)                                     # occurrences reproduced
        if h > 0:                                                # found at least once
            found_unique += 1
        if h < r:                                                # some occurrences missed
            missed.append(f"{term} ({h}/{r})")
    return {
        "terms_unique": f"{found_unique}/{total_unique}",
        "terms_unique_pct": found_unique / max(total_unique, 1),
        "terms_occ_pct": got_occ / max(total_occ, 1),
        "missed_terms": missed,
    }


def top_substitutions(reference: str, hypothesis: str, n: int = 25) -> list:
    """Most frequent word swaps (reference word -> model word), to see what goes wrong."""
    ref, hyp = normalize(reference), normalize(hypothesis)       # normalized texts
    out = jiwer.process_words(ref, hyp)                          # word alignment
    pairs = Counter()                                            # (ref_word, hyp_word) -> count
    r_words, h_words = out.references[0], out.hypotheses[0]      # aligned token lists
    for chunk in out.alignments[0]:                              # each aligned block
        if chunk.type == "substitute":                           # only substitutions
            for i, j in zip(range(chunk.ref_start_idx, chunk.ref_end_idx),
                            range(chunk.hyp_start_idx, chunk.hyp_end_idx)):
                pairs[(r_words[i], h_words[j])] += 1             # count the swap
    return pairs.most_common(n)                                  # most common first


def score_all(reference: str, hypothesis: str, terms: list) -> dict:
    """All metrics for one system in one dict."""
    return {**wer_cer(reference, hypothesis), **term_scores(reference, hypothesis, terms)}

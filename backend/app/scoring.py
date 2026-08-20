"""ATS scoring: weighted blend of hard keyword coverage, semantic coverage, and
formatting/parse-safety. See README for the formula and weight rationale."""

import re
from typing import Callable

import numpy as np

from app.normalize import ALIASES, CANONICAL_FORMS

# backend/eval/sweep.py swept threshold 0.60-0.85 (step 0.01) and a grid of
# weight combinations around these defaults against the labeled synthetic
# eval set. Result: this exact config (0.72 / 0.5-0.35-0.15) is tied for the
# best pairwise-ordering accuracy and Spearman correlation found (100% /
# 0.961) -- the whole swept threshold range scored identically on this set,
# so the sweep found no evidence to move off these defaults. See
# eval/sweep.py's module docstring: this is directional on a 12-entry
# synthetic set, not a definitive calibration.
WEIGHTS = {"keyword": 0.5, "semantic": 0.35, "formatting": 0.15}
SEMANTIC_MATCH_THRESHOLD = 0.72
BORDERLINE_MARGIN = 0.05

_WORD_RE = re.compile(r"[a-zA-Z0-9+#.]+")
_BULLET_START_RE = re.compile(r"^[•\-–*▪◆➤❖✦]\s+|^\d+[.)]\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def _normalize_word(word: str) -> str:
    w = word.lower()
    if w in ALIASES:
        return ALIASES[w]
    if w in CANONICAL_FORMS:
        # Already a canonical base form (e.g. "kubernetes" typed out in full,
        # not the "k8s" alias) -- the suffix stemmer below would otherwise
        # wrongly treat words like this as an "-es" plural and truncate them.
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("es") and len(w) > 3:
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    return w


def _words(text: str) -> list[str]:
    return [_normalize_word(w) for w in _WORD_RE.findall(text)]


def _chunk_resume(resume_text: str) -> list[str]:
    """Split resume text into embedding-comparison units on bullet boundaries
    instead of raw lines, so a bullet that wraps onto a second line (no bullet
    marker of its own) stays one chunk instead of being fragmented into two
    incomplete halves. A run of lines with no bullet marker at all (e.g. a
    summary paragraph) is kept together and then split by sentence instead."""
    chunks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            chunks.append(" ".join(current).strip())
            current.clear()

    for raw_line in resume_text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if _BULLET_START_RE.match(line) or not current:
            flush()
            current.append(_BULLET_START_RE.sub("", line))
        else:
            current.append(line)
    flush()

    final_chunks: list[str] = []
    for chunk in chunks:
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(chunk) if s.strip()]
        final_chunks.extend(sentences if len(sentences) > 1 else [chunk])
    return final_chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


def _contains_contiguous_sequence(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def keyword_coverage(keywords: list[str], resume_text: str) -> tuple[float, list[str], list[str]]:
    """Single-word keywords match by stemmed-token membership anywhere in the resume.
    Multi-word keywords require the stemmed phrase to appear as a contiguous sequence
    in the resume's stemmed token stream — bag-of-words containment alone would match
    "REST API testing" against a resume with those three words scattered far apart,
    which over-matches and under-reports genuine gaps.

    Both the resume and the keywords go through the same alias-aware stemmer
    (see app/normalize.py), so e.g. "k8s" in a resume matches a JD keyword
    "Kubernetes". Keywords are deduped by their canonicalized form after that
    mapping, so a JD that yields both "K8s" and "Kubernetes" as separate
    extracted keywords is only scored once."""
    resume_tokens = _words(resume_text)
    resume_word_set = set(resume_tokens)
    matched, missing = [], []
    seen_canonical: set[tuple[str, ...]] = set()
    for kw in keywords:
        kw_words = tuple(w for w in _words(kw) if w)
        if not kw_words:
            missing.append(kw)
            continue
        if kw_words in seen_canonical:
            continue
        seen_canonical.add(kw_words)
        if len(kw_words) == 1:
            is_match = kw_words[0] in resume_word_set
        else:
            is_match = _contains_contiguous_sequence(resume_tokens, list(kw_words))
        (matched if is_match else missing).append(kw)
    total = len(matched) + len(missing)
    score = 100.0 * len(matched) / total if total else 100.0
    return score, matched, missing


def semantic_coverage(
    missing_keywords: list[str],
    resume_text: str,
    embed_fn: Callable[[list[str]], list[list[float]]],
    threshold: float = SEMANTIC_MATCH_THRESHOLD,
    total_keywords: int | None = None,
) -> tuple[float, list[str], dict[str, float]]:
    """For keywords that failed hard matching, check paraphrase-level presence via
    embeddings. Returns (score, gap_candidates, similarity_by_keyword). gap_candidates
    are keywords that failed BOTH hard match and the semantic threshold — genuinely
    absent skills.

    The aggregate score is credited over `total_keywords` (every JD keyword), with
    each hard-matched keyword (not in `missing_keywords`) counted as a perfect 1.0
    match and each missing keyword contributing its best cosine similarity. Averaging
    only over the missing keywords understated semantic_score whenever most keywords
    were already hard-matched, since those "obviously covered" keywords never
    contributed to the average. Defaults to len(missing_keywords) so callers that
    don't track the full keyword set keep the old missing-only average."""
    total = total_keywords if total_keywords is not None else len(missing_keywords)
    matched_count = max(total - len(missing_keywords), 0)

    if not missing_keywords:
        return 100.0, [], {}

    resume_chunks = _chunk_resume(resume_text)
    if not resume_chunks:
        score = 100.0 * matched_count / total if total else 0.0
        return score, list(missing_keywords), {kw: 0.0 for kw in missing_keywords}

    resume_embeddings = embed_fn(resume_chunks)
    keyword_embeddings = embed_fn(missing_keywords)

    similarities: dict[str, float] = {}
    gap_candidates: list[str] = []
    for kw, kw_vec in zip(missing_keywords, keyword_embeddings):
        best = max((cosine_similarity(kw_vec, r) for r in resume_embeddings), default=0.0)
        similarities[kw] = best
        if best < threshold:
            gap_candidates.append(kw)

    score = 100.0 * (matched_count + sum(similarities.values())) / total if total else 100.0
    return score, gap_candidates, similarities


_STANDARD_HEADINGS = ["experience", "education", "skills"]
_UNUSUAL_BULLET_RE = re.compile(r"[▪◆➤❖✦]")
_COLUMN_GAP_RE = re.compile(r"[ \t]{3,}\S+[ \t]{3,}\S+")


def formatting_coverage(resume_text: str) -> tuple[float, list[str]]:
    """Heuristic parse-safety check — no NIM call. Flags things that commonly break
    ATS parsers when a resume was exported from a table/column layout."""
    issues: list[str] = []
    score = 100.0
    lower = resume_text.lower()

    for heading in _STANDARD_HEADINGS:
        if heading not in lower:
            issues.append(f"Missing standard section heading: '{heading.title()}'")
            score -= 10

    if _COLUMN_GAP_RE.search(resume_text):
        issues.append("Multi-column/table-like spacing detected — ATS parsers often misread tables")
        score -= 15

    if "\t" in resume_text:
        issues.append("Contains tab characters — often a sign of a table or multi-column layout")
        score -= 10

    if _UNUSUAL_BULLET_RE.search(resume_text):
        issues.append("Uses non-standard bullet glyphs that some ATS parsers may drop")
        score -= 5

    lines = [line for line in resume_text.split("\n") if line.strip()]
    if any(len(line) > 400 for line in lines):
        issues.append("Extremely long unbroken lines detected — may indicate missing line breaks")
        score -= 10

    if len(lines) < 3:
        issues.append("Very few line breaks — content may not parse into distinct sections")
        score -= 15

    return max(0.0, min(100.0, score)), issues


def score_resume(
    jd_keywords: list[str],
    resume_text: str,
    embed_fn: Callable[[list[str]], list[list[float]]],
    semantic_threshold: float = SEMANTIC_MATCH_THRESHOLD,
    weights: dict[str, float] | None = None,
) -> dict:
    """semantic_threshold and weights default to the shipped constants above;
    they're only overridden by backend/eval/sweep.py to recalibrate against
    the labeled eval set without duplicating this function's logic."""
    weights = weights or WEIGHTS
    keyword_score, matched_keywords, missing_keywords = keyword_coverage(jd_keywords, resume_text)
    total_keywords = len(matched_keywords) + len(missing_keywords)
    # Use the deduped keyword count (matched + missing), not len(jd_keywords), so
    # the semantic average lines up with keyword_coverage's own denominator.
    semantic_score, gap_candidates, similarities = semantic_coverage(
        missing_keywords,
        resume_text,
        embed_fn,
        threshold=semantic_threshold,
        total_keywords=total_keywords,
    )
    formatting_score, formatting_issues = formatting_coverage(resume_text)

    ats_score = round(
        weights["keyword"] * keyword_score
        + weights["semantic"] * semantic_score
        + weights["formatting"] * formatting_score
    )

    borderline_count = sum(
        1 for sim in similarities.values() if abs(sim - semantic_threshold) <= BORDERLINE_MARGIN
    )
    confidence = {
        "borderline_keyword_count": borderline_count,
        "hard_match_fraction": round(len(matched_keywords) / total_keywords, 3) if total_keywords else 1.0,
        "total_keywords": total_keywords,
    }

    return {
        "ats_score": ats_score,
        "confidence": confidence,
        "component_breakdown": {
            "keyword_score": round(keyword_score, 1),
            "semantic_score": round(semantic_score, 1),
            "formatting_score": round(formatting_score, 1),
            "keyword_weight": weights["keyword"],
            "semantic_weight": weights["semantic"],
            "formatting_weight": weights["formatting"],
        },
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "gap_candidates": gap_candidates,
        "formatting_issues": formatting_issues,
    }

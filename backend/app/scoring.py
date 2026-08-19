"""ATS scoring: weighted blend of hard keyword coverage, semantic coverage, and
formatting/parse-safety. See README for the formula and weight rationale."""

import re
from typing import Callable

import numpy as np

WEIGHTS = {"keyword": 0.5, "semantic": 0.35, "formatting": 0.15}
SEMANTIC_MATCH_THRESHOLD = 0.72

_WORD_RE = re.compile(r"[a-zA-Z0-9+#.]+")


def _normalize_word(word: str) -> str:
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("es") and len(w) > 3:
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    return w


def _words(text: str) -> list[str]:
    return [_normalize_word(w) for w in _WORD_RE.findall(text)]


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
    which over-matches and under-reports genuine gaps."""
    resume_tokens = _words(resume_text)
    resume_word_set = set(resume_tokens)
    matched, missing = [], []
    for kw in keywords:
        kw_words = [w for w in _words(kw) if w]
        if not kw_words:
            missing.append(kw)
            continue
        if len(kw_words) == 1:
            is_match = kw_words[0] in resume_word_set
        else:
            is_match = _contains_contiguous_sequence(resume_tokens, kw_words)
        (matched if is_match else missing).append(kw)
    score = 100.0 * len(matched) / len(keywords) if keywords else 100.0
    return score, matched, missing


def semantic_coverage(
    missing_keywords: list[str],
    resume_text: str,
    embed_fn: Callable[[list[str]], list[list[float]]],
    threshold: float = SEMANTIC_MATCH_THRESHOLD,
) -> tuple[float, list[str], dict[str, float]]:
    """For keywords that failed hard matching, check paraphrase-level presence via
    embeddings. Returns (score, gap_candidates, similarity_by_keyword). gap_candidates
    are keywords that failed BOTH hard match and the semantic threshold — genuinely
    absent skills."""
    if not missing_keywords:
        return 100.0, [], {}

    resume_lines = [line.strip() for line in resume_text.split("\n") if line.strip()]
    if not resume_lines:
        return 0.0, list(missing_keywords), {kw: 0.0 for kw in missing_keywords}

    resume_embeddings = embed_fn(resume_lines)
    keyword_embeddings = embed_fn(missing_keywords)

    similarities: dict[str, float] = {}
    gap_candidates: list[str] = []
    for kw, kw_vec in zip(missing_keywords, keyword_embeddings):
        best = max((cosine_similarity(kw_vec, r) for r in resume_embeddings), default=0.0)
        similarities[kw] = best
        if best < threshold:
            gap_candidates.append(kw)

    score = 100.0 * (sum(similarities.values()) / len(similarities))
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
) -> dict:
    keyword_score, matched_keywords, missing_keywords = keyword_coverage(jd_keywords, resume_text)
    semantic_score, gap_candidates, _similarities = semantic_coverage(
        missing_keywords, resume_text, embed_fn
    )
    formatting_score, formatting_issues = formatting_coverage(resume_text)

    ats_score = round(
        WEIGHTS["keyword"] * keyword_score
        + WEIGHTS["semantic"] * semantic_score
        + WEIGHTS["formatting"] * formatting_score
    )

    return {
        "ats_score": ats_score,
        "component_breakdown": {
            "keyword_score": round(keyword_score, 1),
            "semantic_score": round(semantic_score, 1),
            "formatting_score": round(formatting_score, 1),
            "keyword_weight": WEIGHTS["keyword"],
            "semantic_weight": WEIGHTS["semantic"],
            "formatting_weight": WEIGHTS["formatting"],
        },
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "gap_candidates": gap_candidates,
        "formatting_issues": formatting_issues,
    }

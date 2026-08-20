import pytest

from app.scoring import (
    cosine_similarity,
    formatting_coverage,
    keyword_coverage,
    score_resume,
    semantic_coverage,
)

RESUME_TEXT = """Experience
- Built REST APIs in Python using FastAPI for a fintech startup
- Led a team of 3 engineers on a data pipeline migration
- Wrote unit tests with pytest, achieving 90% coverage

Education
BS in Computer Science

Skills
Python, SQL, Docker, Git
"""


def test_keyword_coverage_matches_verbatim_and_stemmed():
    score, matched, missing = keyword_coverage(["Python", "APIs", "Kubernetes"], RESUME_TEXT)
    assert "Python" in matched
    assert "APIs" in matched  # stems to "api", present via "REST APIs" -> "api"
    assert "Kubernetes" in missing
    assert round(score) == round(100 * 2 / 3)


def test_keyword_coverage_empty_keywords_is_full_score():
    score, matched, missing = keyword_coverage([], RESUME_TEXT)
    assert score == 100.0
    assert matched == []
    assert missing == []


def test_keyword_coverage_multiword_scattered_does_not_match():
    """Regression: bag-of-words containment used to match "REST API testing"
    against a resume containing those three words far apart, over-matching and
    under-reporting genuine gaps. A scattered occurrence must NOT count."""
    scattered = (
        "Experience\n"
        "- Built a REST service in Python\n"
        "- Wrote extensive API documentation\n"
        "- Ran manual testing before every release\n"
        "\nEducation\nBS in Computer Science\n\nSkills\nPython\n"
    )
    score, matched, missing = keyword_coverage(["REST API testing"], scattered)
    assert "REST API testing" in missing
    assert "REST API testing" not in matched


def test_keyword_coverage_multiword_adjacent_does_match():
    adjacent = (
        "Experience\n"
        "- Built REST API testing suites for a fintech startup\n"
        "\nEducation\nBS in Computer Science\n\nSkills\nPython\n"
    )
    score, matched, missing = keyword_coverage(["REST API testing"], adjacent)
    assert "REST API testing" in matched
    assert "REST API testing" not in missing


def test_keyword_coverage_multiword_tolerates_case_and_stemming():
    adjacent = "Experience\n- built rest apis testing tools\nEducation\nBS\nSkills\nPython\n"
    score, matched, missing = keyword_coverage(["REST API Testing"], adjacent)
    assert "REST API Testing" in matched


def test_cosine_similarity_identical_vectors_is_one():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_semantic_coverage_no_missing_keywords_is_full_score():
    score, gaps, sims = semantic_coverage([], RESUME_TEXT, embed_fn=lambda texts: [])
    assert score == 100.0
    assert gaps == []


def test_semantic_coverage_uses_embeddings_to_find_gap_candidates():
    # Fake embed_fn: gives high similarity to "backend" (paraphrase of an existing
    # resume line) and near-zero similarity to "Kubernetes" (genuinely absent).
    def fake_embed(texts):
        vectors = []
        for t in texts:
            if "backend" in t.lower() or "api" in t.lower():
                vectors.append([1.0, 0.0])
            elif "kubernetes" in t.lower():
                vectors.append([0.0, 1.0])
            else:
                vectors.append([1.0, 0.0])  # resume lines default to the "api" cluster
        return vectors

    score, gap_candidates, sims = semantic_coverage(
        ["backend development", "Kubernetes"], RESUME_TEXT, embed_fn=fake_embed
    )
    assert "Kubernetes" in gap_candidates
    assert "backend development" not in gap_candidates
    assert sims["backend development"] > sims["Kubernetes"]


def test_semantic_coverage_credits_hard_matched_keywords_in_aggregate():
    """Regression: the aggregate score used to average only over missing_keywords,
    so a JD where most keywords already hard-matched got no credit for them and
    could score as low as its single worst semantic gap. total_keywords=3 with
    2 already hard-matched (not in missing_keywords) should credit those 2 as
    perfect matches: (2*1.0 + 0.0) / 3, not 0.0 / 1."""

    def fake_embed(texts):
        return [[0.0, 0.0] for _ in texts]  # zero similarity for the one missing keyword

    score, gap_candidates, sims = semantic_coverage(
        ["Kubernetes"], RESUME_TEXT, embed_fn=fake_embed, total_keywords=3
    )
    assert score == pytest.approx(100.0 * 2 / 3)
    assert "Kubernetes" in gap_candidates  # threshold behavior unchanged


def test_semantic_coverage_defaults_to_missing_only_denominator():
    """Without total_keywords, behavior is unchanged from before Stage 1 (existing
    direct callers of semantic_coverage that don't track the full keyword count)."""

    def fake_embed(texts):
        return [[0.0, 0.0] for _ in texts]

    score, gap_candidates, sims = semantic_coverage(["Kubernetes"], RESUME_TEXT, embed_fn=fake_embed)
    assert score == 0.0


def test_score_resume_semantic_score_credits_hard_matched_keywords():
    def fake_embed(texts):
        return [[0.0, 0.0] for _ in texts]  # zero similarity for anything missing

    result = score_resume(["Python", "Kubernetes"], RESUME_TEXT, embed_fn=fake_embed)
    # "Python" hard-matches (Skills line), "Kubernetes" doesn't and has zero semantic
    # similarity -- semantic_score should reflect 1 of 2 JD keywords covered, not 0.
    assert result["component_breakdown"]["semantic_score"] == pytest.approx(50.0)


def test_formatting_coverage_flags_missing_headings():
    score, issues = formatting_coverage("Just a single line resume with no structure.")
    assert score < 100.0
    assert any("heading" in issue.lower() for issue in issues)
    assert any("line" in issue.lower() for issue in issues)


def test_formatting_coverage_clean_resume_scores_high():
    score, issues = formatting_coverage(RESUME_TEXT)
    assert score == 100.0
    assert issues == []


def test_formatting_coverage_flags_table_like_spacing():
    tabular = "Experience\nEducation\nSkills\nPython        SQL        Docker\n"
    score, issues = formatting_coverage(tabular)
    assert score < 100.0
    assert any("column" in issue.lower() or "table" in issue.lower() for issue in issues)


def test_score_resume_blends_components_with_documented_weights():
    def fake_embed(texts):
        return [[1.0, 0.0] for _ in texts]  # everything "matches" semantically

    result = score_resume(["Python", "Docker"], RESUME_TEXT, embed_fn=fake_embed)
    assert result["ats_score"] == round(
        0.5 * result["component_breakdown"]["keyword_score"]
        + 0.35 * result["component_breakdown"]["semantic_score"]
        + 0.15 * result["component_breakdown"]["formatting_score"]
    )
    assert 0 <= result["ats_score"] <= 100
    assert result["component_breakdown"]["keyword_weight"] == 0.5
    assert result["component_breakdown"]["semantic_weight"] == 0.35
    assert result["component_breakdown"]["formatting_weight"] == 0.15

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

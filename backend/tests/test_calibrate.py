import pytest

from eval.calibrate import (
    load_dataset,
    pairwise_ordering_accuracy,
    spearman,
    stub_embed,
)


def test_load_dataset_has_expected_shape():
    pairs = load_dataset()
    assert 12 <= len(pairs) <= 15
    labels = {p["label"] for p in pairs}
    assert labels == {"strong", "medium", "poor"}
    for p in pairs:
        assert p["jd_keywords"]
        assert p["resume"]


def test_stub_embed_returns_fixed_dimension_vectors_across_separate_calls():
    """Regression: an earlier version built a per-call vocabulary, so two
    separate embed_fn calls (as semantic_coverage makes: one for resume lines,
    one for keywords) produced vectors of different lengths and cosine
    similarity crashed with a shape mismatch."""
    resume_vectors = stub_embed(["Built REST APIs in Python"])
    keyword_vectors = stub_embed(["Kubernetes"])
    assert len(resume_vectors[0]) == len(keyword_vectors[0])


def test_stub_embed_is_deterministic_across_runs():
    assert stub_embed(["Python developer"]) == stub_embed(["Python developer"])


def test_spearman_perfect_correlation():
    assert spearman([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)


def test_spearman_perfect_inverse_correlation():
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)


def test_pairwise_ordering_accuracy_all_correct():
    accuracy, correct, total = pairwise_ordering_accuracy([90, 50, 10], [2, 1, 0])
    assert accuracy == 1.0
    assert (correct, total) == (3, 3)


def test_pairwise_ordering_accuracy_detects_a_misordering():
    # label 2 (strong) scores lower than label 0 (poor) -- a real miscalibration
    accuracy, correct, total = pairwise_ordering_accuracy([10, 50, 90], [2, 1, 0])
    assert accuracy < 1.0


def test_calibration_dataset_rank_orders_correctly():
    """The actual calibration claim this app makes in its README: the scoring
    formula rank-orders the labeled synthetic set correctly."""
    from app.scoring import score_resume

    pairs = load_dataset()
    label_rank = {"poor": 0, "medium": 1, "strong": 2}
    scores = []
    labels = []
    for entry in pairs:
        result = score_resume(entry["jd_keywords"], entry["resume"], embed_fn=stub_embed)
        scores.append(result["ats_score"])
        labels.append(label_rank[entry["label"]])
    accuracy, _correct, _total = pairwise_ordering_accuracy(scores, labels)
    assert accuracy >= 0.9

from app.scoring import SEMANTIC_MATCH_THRESHOLD, WEIGHTS
from eval.calibrate import load_dataset
from eval.sweep import THRESHOLD_RANGE, WEIGHT_GRID, _evaluate


def test_threshold_range_spans_060_to_085():
    assert THRESHOLD_RANGE[0] == 0.60
    assert THRESHOLD_RANGE[-1] == 0.85
    assert round(SEMANTIC_MATCH_THRESHOLD, 2) in THRESHOLD_RANGE


def test_weight_grid_includes_current_default_and_sums_to_one():
    assert WEIGHTS in WEIGHT_GRID
    for weights in WEIGHT_GRID:
        assert round(sum(weights.values()), 6) == 1.0


def test_evaluate_returns_accuracy_and_spearman_in_valid_ranges():
    pairs = load_dataset()
    accuracy, corr = _evaluate(pairs, SEMANTIC_MATCH_THRESHOLD, WEIGHTS)
    assert 0.0 <= accuracy <= 1.0
    assert -1.0 <= corr <= 1.0

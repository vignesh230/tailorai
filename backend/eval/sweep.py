"""Sweep the semantic-match threshold (and a small grid of the three ATS
weights) over the labeled synthetic eval set, to check whether the shipped
defaults (0.72 threshold, 0.5/0.35/0.15 weights, see app/scoring.py) are
near-optimal for rank-ordering strong/medium/poor fit, or whether another
combination scores better on this set.

This is DIRECTIONAL, not definitive: labeled_pairs.json is a 12-entry
SYNTHETIC dataset (see eval/README.md), not real applicant data, so the
"best" config found here is a hint for where to look, not a config to
blindly ship. This script only reports; it does not change any default in
app/scoring.py.

Run from backend/:  python -m eval.sweep
"""
from app.scoring import SEMANTIC_MATCH_THRESHOLD, WEIGHTS, score_resume
from eval.calibrate import (
    LABEL_RANK,
    load_dataset,
    pairwise_ordering_accuracy,
    spearman,
    stub_embed,
)

THRESHOLD_RANGE = [round(0.60 + 0.01 * i, 2) for i in range(26)]  # 0.60 .. 0.85

# A coarse grid around the current weights (each sums to 1.0). Kept small --
# fine-grained weight search on a 12-entry set would just fit noise.
WEIGHT_GRID = [
    {"keyword": 0.5, "semantic": 0.35, "formatting": 0.15},
    {"keyword": 0.6, "semantic": 0.3, "formatting": 0.1},
    {"keyword": 0.5, "semantic": 0.4, "formatting": 0.1},
    {"keyword": 0.4, "semantic": 0.45, "formatting": 0.15},
    {"keyword": 0.45, "semantic": 0.4, "formatting": 0.15},
    {"keyword": 0.55, "semantic": 0.3, "formatting": 0.15},
]


def _evaluate(pairs: list[dict], threshold: float, weights: dict[str, float]) -> tuple[float, float]:
    scores, labels = [], []
    for entry in pairs:
        result = score_resume(
            entry["jd_keywords"],
            entry["resume"],
            embed_fn=stub_embed,
            semantic_threshold=threshold,
            weights=weights,
        )
        scores.append(result["ats_score"])
        labels.append(LABEL_RANK[entry["label"]])
    accuracy, _correct, _total = pairwise_ordering_accuracy(scores, labels)
    corr = spearman([float(s) for s in scores], [float(l) for l in labels])
    return accuracy, corr


def main() -> None:
    pairs = load_dataset()

    print("Threshold sweep (weights held at current defaults):")
    print(f"{'threshold':>9} {'accuracy':>9} {'spearman':>9}")
    threshold_results = []
    for threshold in THRESHOLD_RANGE:
        accuracy, corr = _evaluate(pairs, threshold, WEIGHTS)
        threshold_results.append({"threshold": threshold, "accuracy": accuracy, "spearman": corr})
        marker = "  <- current default" if threshold == SEMANTIC_MATCH_THRESHOLD else ""
        print(f"{threshold:>9.2f} {accuracy * 100:>8.1f}% {corr:>9.3f}{marker}")

    best_threshold_row = max(threshold_results, key=lambda r: (r["accuracy"], r["spearman"]))

    print()
    print("Weight sweep (threshold held at current default):")
    print(f"{'keyword':>8} {'semantic':>9} {'formatting':>11} {'accuracy':>9} {'spearman':>9}")
    weight_results = []
    for weights in WEIGHT_GRID:
        accuracy, corr = _evaluate(pairs, SEMANTIC_MATCH_THRESHOLD, weights)
        weight_results.append({"weights": weights, "accuracy": accuracy, "spearman": corr})
        marker = "  <- current default" if weights == WEIGHTS else ""
        print(
            f"{weights['keyword']:>8.2f} {weights['semantic']:>9.2f} {weights['formatting']:>11.2f} "
            f"{accuracy * 100:>8.1f}% {corr:>9.3f}{marker}"
        )

    best_weight_row = max(weight_results, key=lambda r: (r["accuracy"], r["spearman"]))

    print()
    print(
        f"Best threshold found: {best_threshold_row['threshold']:.2f} "
        f"({best_threshold_row['accuracy']:.1%} accuracy, {best_threshold_row['spearman']:.3f} Spearman)"
    )
    print(
        f"Best weights found: {best_weight_row['weights']} "
        f"({best_weight_row['accuracy']:.1%} accuracy, {best_weight_row['spearman']:.3f} Spearman)"
    )
    print()
    print("NOTE: this eval set is a 12-entry SYNTHETIC dataset, not real applicant")
    print("data -- treat any 'best' config above as directional, not definitive.")
    print("The shipped defaults in app/scoring.py are not changed by this script.")


if __name__ == "__main__":
    main()

"""Calibration harness for the ATS scoring formula (0.5 keyword / 0.35 semantic /
0.15 formatting weights, 0.72 semantic match threshold).

Runs score_resume() over a small, hand-labeled synthetic dataset
(labeled_pairs.json, see its "_note" field) and checks whether ats_score
rank-orders "strong" > "medium" > "poor" fit labels correctly. Uses a
deterministic word-overlap stub for embed_fn so this runs entirely offline,
no NIM key or network needed. This exercises the SCORING FORMULA's
weighting and threshold, not NIM's embedding quality, which is a separate,
already-live-tested concern (see README's NIM connectivity notes).

Run from backend/:  python -m eval.calibrate
"""
import json
import zlib
from pathlib import Path
from statistics import mean

from app.scoring import score_resume

LABEL_RANK = {"poor": 0, "medium": 1, "strong": 2}
STUB_EMBED_DIM = 256


def stub_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic fixed-dimension bag-of-words hash vector, so cosine
    similarity reflects shared vocabulary between two texts -- a weak but
    reproducible, fully offline stand-in for a real embedding model. Uses
    zlib.crc32 (not Python's built-in hash()) so the vectors are stable across
    runs regardless of PYTHONHASHSEED. Sufficient to validate the scoring
    formula's relative behavior across a labeled set; not a claim about real
    embedding quality. Note: semantic_coverage() calls embed_fn once for
    resume lines and once for keywords, in separate calls -- the vectors must
    share a fixed dimension across calls for cosine similarity between them to
    mean anything, which is why this hashes into a fixed-size vector instead
    of building a per-call vocabulary index."""
    vectors = []
    for text in texts:
        vec = [0.0] * STUB_EMBED_DIM
        for word in text.lower().split():
            word = word.strip(".,()")
            if not word:
                continue
            idx = zlib.crc32(word.encode("utf-8")) % STUB_EMBED_DIM
            vec[idx] += 1.0
        vectors.append(vec)
    return vectors


def load_dataset() -> list[dict]:
    path = Path(__file__).parent / "labeled_pairs.json"
    data = json.loads(path.read_text())
    return data["pairs"]


def _rank(values: list[float]) -> list[float]:
    """Average-rank transform (ties get the mean of their tied ranks), the
    standard input Spearman correlation needs."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation with no scipy dependency."""
    rx, ry = _rank(x), _rank(y)
    mean_rx, mean_ry = mean(rx), mean(ry)
    cov = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    var_x = sum((a - mean_rx) ** 2 for a in rx)
    var_y = sum((b - mean_ry) ** 2 for b in ry)
    denom = (var_x * var_y) ** 0.5
    return cov / denom if denom else 0.0


def pairwise_ordering_accuracy(scores: list[int], labels: list[int]) -> tuple[float, int, int]:
    """Of every pair with different labels, what fraction has the higher-labeled
    entry scoring at least as high as the lower-labeled one?"""
    correct = 0
    total = 0
    for i in range(len(scores)):
        for j in range(i + 1, len(scores)):
            if labels[i] == labels[j]:
                continue
            total += 1
            hi, lo = (i, j) if labels[i] > labels[j] else (j, i)
            if scores[hi] >= scores[lo]:
                correct += 1
    accuracy = correct / total if total else 0.0
    return accuracy, correct, total


def main() -> None:
    pairs = load_dataset()
    scores: list[int] = []
    labels: list[int] = []

    print(f"{'id':<18} {'label':<8} {'ats_score':>9}")
    for entry in pairs:
        result = score_resume(entry["jd_keywords"], entry["resume"], embed_fn=stub_embed)
        scores.append(result["ats_score"])
        labels.append(LABEL_RANK[entry["label"]])
        print(f"{entry['id']:<18} {entry['label']:<8} {result['ats_score']:>9}")

    corr = spearman([float(s) for s in scores], [float(l) for l in labels])
    accuracy, correct, total = pairwise_ordering_accuracy(scores, labels)

    print()
    print(f"Spearman rank correlation (ats_score vs label): {corr:.3f}")
    print(f"Pairwise ordering accuracy: {accuracy:.1%} ({correct}/{total} label pairs correctly ordered)")


if __name__ == "__main__":
    main()

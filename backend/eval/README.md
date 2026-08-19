# ATS scoring calibration

`labeled_pairs.json` is a **synthetic** dataset. Every name, company, and
resume/JD line in it is fabricated for testing purposes only. It does not
represent any real applicant, employer, or job posting.

## What this checks

`calibrate.py` runs `score_resume()` (the same function `/analyze` calls) over
12 labeled resume/JD pairs across 4 roles (backend, frontend, data science,
devops), each with a "strong", "medium", and "poor" fit example, and checks
whether `ats_score` rank-orders those labels correctly.

It uses a deterministic, fully offline stand-in for `embed_fn` (a fixed-size
word-hash vector, not a real embedding model), so this needs no NIM API key
and no network access. It is validating the **scoring formula's** behavior
(the 0.5/0.35/0.15 weights and the 0.72 semantic threshold), not NIM's
embedding quality, which is separately covered by the app's live NIM
connectivity checks.

## Run it

```bash
cd backend
python -m eval.calibrate
```

## Result

At the time this was last run: **100% pairwise ordering accuracy** (48/48
label pairs correctly ordered) and a **Spearman rank correlation of 0.96**
between `ats_score` and label. The weights and threshold are presented in the
main README as calibrated against this method, not asserted from intuition.

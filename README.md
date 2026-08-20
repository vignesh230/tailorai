# TailorAI

AI resume-tailoring app with ATS scoring. Paste a resume and a job description,
get back a 0–100 ATS score with a component breakdown, matched/missing keywords,
AI-tailored bullet suggestions grounded only in what's actually on the resume,
and honest warnings (with suggested sample projects) for skills that are
genuinely missing.

**Live URL:** _(deploy and drop the link here)_

## Architecture

```
frontend (Next.js App Router)  --->  backend (FastAPI)  --->  Postgres
                                             |
                                             v
                                   NVIDIA NIM (OpenAI-compatible API)
```

- **Frontend** — Next.js (App Router) + TypeScript + Tailwind. No component
  library. A thin `lib/api.ts` fetch wrapper attaches the JWT from
  `localStorage`; `lib/auth.tsx` is a minimal auth context. The paste → analyze
  → results loop is entirely client-driven; the result of `POST /analyze` is
  stashed in `sessionStorage` and read back on the results page (no extra
  `GET /analyses/{id}` endpoint — the client already has the full object from
  the POST response).
- **Backend** — FastAPI, synchronous (no async DB/HTTP layer — not needed at
  this scale, and it keeps the code simpler to read and test). SQLAlchemy 2.0 +
  Alembic against Postgres.
- **Auth** — JWT via `pyjwt`, password hashing via `bcrypt` directly. Both are
  maintained libraries; no hand-rolled crypto.
- **AI layer** — a single wrapper module, `backend/app/ai_client.py`,
  instantiates the `openai` Python SDK pointed at NVIDIA NIM's
  OpenAI-compatible endpoint (`base_url=https://integrate.api.nvidia.com/v1`).
  Every chat and embedding call in the app goes through this module. Chat
  calls that should return structured data prompt the model for JSON only and
  parse the response defensively (strip ` ```json ` fences, fall back to a
  regex extraction of the first `{...}`/`[...]` block). All NIM calls retry
  with exponential backoff on transient failures.

## Why FastAPI, why embeddings, how grounding is enforced

- **Why FastAPI** — Pydantic request/response models double as both input
  validation and the OpenAPI schema `/docs` UI, which matters a lot when the
  frontend and backend are built in the same session against a moving schema.
- **Why embeddings** — hard keyword matching alone misses a resume that says
  "orchestrated containerized services" when the JD asks for "Kubernetes."
  Embedding both the JD requirements and the resume's lines and comparing
  cosine similarity catches that paraphrase-level coverage without an LLM call
  per comparison.
- **How grounding is enforced** — the tailored-bullet prompt is only ever given
  keywords that (a) are *not* a hard match in the resume text but (b) *did*
  clear the semantic similarity threshold against some existing resume line —
  i.e., keywords the resume already substantively supports, just not
  verbatim. Keywords that fail both checks are true gaps: they never reach the
  bullet-tailoring prompt, and instead the model is asked (in a separate call)
  to suggest a concrete sample project to close that specific gap. This keeps
  fabrication out of the tailored bullets by construction, not just by prompt
  instruction.

## ATS scoring formula

`ats_score = round(0.5 × keyword_score + 0.35 × semantic_score + 0.15 × formatting_score)`, 0–100.

| Component | Weight | What it measures |
|---|---|---|
| **Keyword coverage** | 0.5 | NIM extracts required skills/keywords from the JD as JSON. Single-word keywords match by stemmed-token membership anywhere in the resume (handles simple plurals/suffixes). Multi-word keywords require the stemmed phrase to appear as a *contiguous* sequence in the resume — scattered-but-present words don't count, since that over-matched phrases like "REST API testing" against a resume that merely mentioned REST, API, and testing in unrelated lines. This is the most literal, ATS-like signal, so it carries the most weight. |
| **Semantic coverage** | 0.35 | For every keyword that failed the hard match, embed it and every resume line (NIM embeddings) and take the best cosine similarity. The average of those best-matches is the semantic score. A similarity ≥ 0.72 counts as "covered" (paraphrase-level); below that, the keyword becomes a genuine gap candidate. |
| **Formatting / parse-safety** | 0.15 | Pure heuristics, no NIM call: missing standard section headings (Experience/Education/Skills), multi-space/tab column-like spacing (table risk), non-standard bullet glyphs, extremely long unbroken lines, or too few line breaks overall. Starts at 100, loses points per flag. |

`matched_keywords` / `missing_keywords` come from the hard-match step.
`gap_flags` are the subset of `missing_keywords` that *also* failed the
semantic threshold — i.e., skills genuinely absent from the resume, each
paired with an AI-suggested sample project and a one-line reason it matters
for that specific job description. Everything else missing-but-semantically-
present becomes a candidate for a tailored bullet rewrite instead.

## Calibration

The 0.5/0.35/0.15 weights and the 0.72 semantic-match threshold are presented
as calibrated, not guessed. `backend/eval/` holds the method: a 12-entry
synthetic labeled dataset (`labeled_pairs.json`, resume/JD pairs across 4
roles each labeled "strong"/"medium"/"poor") and a script
(`calibrate.py`) that runs the real `score_resume()` over it with a
deterministic offline stand-in for the embedding call, and reports whether
`ats_score` rank-orders the labels correctly.

```bash
cd backend
python -m eval.calibrate
```

Last run: **100% pairwise ordering accuracy** and a **0.961 Spearman
correlation** between `ats_score` and label. See `backend/eval/README.md` for
the full method and why the dataset is explicitly synthetic.

`eval/sweep.py` sweeps the semantic threshold (0.60-0.85) and a small grid of
weight combinations against the same set to check whether a different config
scores better:

```bash
cd backend
python -m eval.sweep
```

Last run found the shipped defaults tied for the best result on this set (the
whole swept threshold range scored identically); see the comment above
`WEIGHTS`/`SEMANTIC_MATCH_THRESHOLD` in `app/scoring.py`. This is directional
on a 12-entry synthetic set, not a definitive calibration -- it did not find
evidence to change the defaults, which is different from proving they're
optimal against real applicant data.

## Quickstart

```bash
cp .env.example .env
# fill in NVIDIA_NIM_API_KEY (https://build.nvidia.com) and a real JWT_SECRET

docker compose up --build
# backend: http://localhost:8000  (docs at /docs)
# postgres: localhost:5432

cd frontend
npm install
npm run dev
# frontend: http://localhost:3000
```

## Tests

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

Tests mock the NIM client entirely (`app.ai_client.chat_json` / `.embed`) and
run against an in-memory SQLite database, so `pytest` needs no live API key
and no Postgres instance. CI (`.github/workflows/tests.yml`) runs the same
suite on every push/PR.

## Project layout

```
backend/    FastAPI app, SQLAlchemy models, Alembic migrations, pytest suite
frontend/   Next.js App Router pages, lib/api.ts + lib/auth.tsx + lib/export.ts
docker-compose.yml   backend + Postgres, one command
.env.example          every required env var, no secrets hardcoded anywhere
```

## Environment variables

See `.env.example`. Required: `DATABASE_URL`, `JWT_SECRET`,
`NVIDIA_NIM_API_KEY`. `NIM_CHAT_MODEL` and `NIM_EMBED_MODEL` are swappable via
env — defaults are `meta/llama-3.1-8b-instruct` and
`nvidia/nv-embedqa-e5-v5`. (A larger chat model like
`meta/llama-3.3-70b-instruct` works too but was consistently slow — 90s+ per
call — under NIM's free tier during testing, and `/analyze` makes up to three
sequential chat calls; the 8B default keeps the full analyze loop to roughly
15–20 seconds.)

`ENVIRONMENT` (default `development`) gates the JWT secret check below — it
does not change any other app behavior.

## Security

- **JWT secret enforcement** — the app boots with a default `JWT_SECRET` in
  development so it works out of the box, but refuses to start with that
  default (or anything under 32 bytes) when `ENVIRONMENT` is set to anything
  other than `development`. Set a real `JWT_SECRET` before deploying anywhere
  that isn't local development.
- **Rate limiting** — `POST /analyze` is limited to 10 requests per minute,
  keyed by the authenticated user (falling back to client IP for
  unauthenticated requests), since each call makes several paid NIM requests.
  Exceeding it returns `429` with a JSON `detail` message.

import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from openai import OpenAIError
from sqlalchemy.orm import Session

from app import ai_client
from app.database import get_db
from app.deps import get_current_user
from app.models import Analysis, JobDescription, Resume, User
from app.rate_limit import limiter
from app.schemas import AnalyzeRequest, AnalysisOut, AnalysisSummary
from app.scoring import score_resume

ANALYZE_RATE_LIMIT = "10/minute"

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analyze"])

MAX_TAILORED_BULLETS = 15
MAX_KEYWORDS = 25
# Pasted job descriptions are often copied straight off a job-board page and
# carry a lot of navigation/UI clutter ("Apply now", "Add to cart", cookie
# banners). A few thousand characters is far more than any real JD's actual
# content needs, and capping it also protects against feeding the model
# enough repetitive noise to spiral into a runaway, never-terminating
# response (observed live: a 36K+ character JSON response that kept
# truncating even after the token budget was grown to its ceiling).
MAX_JD_CHARS = 6000
MAX_RESUME_CHARS = 6000

_BULLET_GLYPH_RE = re.compile(r"^[\s•\-–*]+")
_WHITESPACE_RE = re.compile(r"\s+")
_QUOTE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _normalize_for_grounding(text: str) -> str:
    """Collapse whitespace, strip leading bullet glyphs, and unify quote styles so a
    truthful rewrite isn't falsely rejected over cosmetic formatting differences."""
    text = text.translate(_QUOTE_TRANSLATION)
    text = _BULLET_GLYPH_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text.casefold()


def _find_verbatim_line(candidate: str, resume_text: str) -> str | None:
    """Check whether `candidate` genuinely appears in resume_text, tolerant of
    whitespace/bullet-glyph/quote differences — but always return the actual
    verbatim resume text (never the model's copy), so the exact-substring
    substitution used for export still works."""
    if not candidate:
        return None
    if candidate in resume_text:
        return candidate
    normalized_candidate = _normalize_for_grounding(candidate)
    if not normalized_candidate:
        return None
    for line in resume_text.split("\n"):
        if _normalize_for_grounding(line) == normalized_candidate:
            return line
    return None


def _strip_em_dashes(text: str) -> str:
    """Em dashes are a common tell of AI-generated resume text and some ATS
    parsers mangle them — replace with a plain hyphen. En dashes (used
    legitimately in date ranges like 'Aug 2024 - May 2026') are left alone."""
    return text.replace("—", " - ")


def extract_jd_keywords(jd_text: str) -> list[str]:
    messages = [
        {
            "role": "system",
            "content": (
                "You extract required skills and keywords from job descriptions. "
                "The input may include website navigation, buttons, or boilerplate "
                "(e.g. 'Apply now', 'Add to cart', cookie banners, unrelated site "
                "chrome) mixed in with the actual job description — ignore all of "
                "that and extract keywords ONLY from genuine job requirements. "
                "Respond with JSON only, no prose: {\"keywords\": [\"...\"]}. "
                "Include concrete skills, tools, technologies, certifications, and "
                f"role-specific requirements — at most {MAX_KEYWORDS} items, each a short "
                "phrase. Skip generic filler like 'team player' or 'good communicator'."
            ),
        },
        {"role": "user", "content": jd_text[:MAX_JD_CHARS]},
    ]
    result = ai_client.chat_json(messages)
    keywords = result.get("keywords", []) if isinstance(result, dict) else []
    return [k.strip() for k in keywords if isinstance(k, str) and k.strip()][:MAX_KEYWORDS]


def generate_tailored_bullets(resume_text: str, groundable_keywords: list[str]) -> list[dict]:
    if not groundable_keywords:
        return []
    # The Summary/Objective paragraph is generate_summary_tailoring's job, not this
    # function's — without this exclusion both can independently target the same
    # paragraph and return two conflicting rewrites of it (observed live: one landed
    # in the resume, the other fell into the unmatched "Suggested additions" pile).
    summary_paragraph = _extract_summary_paragraph(resume_text)
    messages = [
        {
            "role": "system",
            "content": (
                "You tailor resume bullets to naturally incorporate specific keywords, "
                "without keyword stuffing and without ever fabricating experience. Only "
                "rewrite a bullet if the keyword can be truthfully grounded in what it "
                "already describes. Never rewrite the Summary or Objective paragraph — "
                "that is handled by a separate step; only rewrite Experience/Projects/"
                "Skills lines. Respond with JSON only, no prose: "
                '{"bullets": [{"section": "<section name or \'Experience\'>", '
                '"original": "<verbatim line copied exactly from the resume>", '
                '"tailored": "<rewritten line>"}]}. '
                f"Include at most {MAX_TAILORED_BULLETS} bullets. If a keyword cannot be "
                "naturally grounded in any existing bullet, omit it entirely — never invent "
                "new experience, employers, tools, or metrics. Do not use em dashes."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Resume:\n{resume_text[:MAX_RESUME_CHARS]}\n\n"
                f"Keywords to naturally incorporate where truthful: {groundable_keywords}"
            ),
        },
    ]
    result = ai_client.chat_json(messages)
    bullets = result.get("bullets", []) if isinstance(result, dict) else []
    grounded: list[dict] = []
    for b in bullets:
        if not isinstance(b, dict) or not b.get("original") or not b.get("tailored"):
            continue
        verbatim = _find_verbatim_line(b["original"], resume_text)
        if not verbatim or verbatim == b["tailored"]:
            continue
        if summary_paragraph and verbatim in summary_paragraph:
            continue  # defense-in-depth: don't just trust the prompt instruction
        grounded.append(
            {
                "section": b.get("section") or "Experience",
                "original": verbatim,  # always the real resume text, never the model's copy
                "tailored": _strip_em_dashes(b["tailored"]),
            }
        )
    return grounded[:MAX_TAILORED_BULLETS]


_SUMMARY_HEADING_RE = re.compile(r"^\s*(summary|objective|profile)\s*$", re.IGNORECASE)
_SECTION_HEADING_RE = re.compile(r"^[A-Za-z][A-Za-z /]{1,30}$")


def _extract_summary_paragraph(resume_text: str) -> str | None:
    """Find the Summary/Objective section (if any) and return the exact verbatim
    substring of resume_text spanning its paragraph — a re-joined/re-wrapped copy
    would no longer be a substring of resume_text, breaking the exact-match
    substitution both here and on the frontend."""
    lines = resume_text.split("\n")
    start = next(
        (i + 1 for i, line in enumerate(lines) if _SUMMARY_HEADING_RE.match(line.strip())), None
    )
    if start is None:
        return None
    while start < len(lines) and not lines[start].strip():
        start += 1  # skip blank lines right after the heading
    end = start
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            break
        # An all-caps short line is almost certainly the next section heading.
        if _SECTION_HEADING_RE.match(stripped) and stripped == stripped.upper():
            break
        end = i + 1
    if end <= start:
        return None
    return "\n".join(lines[start:end])


def generate_summary_tailoring(resume_text: str, jd_text: str) -> list[dict]:
    """Rewrite the resume's Summary/Objective paragraph (if it has one) to better
    emphasize genuinely relevant experience already described elsewhere on the
    resume, in the JD's language where that's truthfully applicable. Returned in
    the same {section, original, tailored} shape as generate_tailored_bullets so
    it flows through the same grounded-substitution and export pipeline."""
    original_summary = _extract_summary_paragraph(resume_text)
    if not original_summary:
        return []
    messages = [
        {
            "role": "system",
            "content": (
                "Rewrite a resume's summary/objective paragraph to better emphasize "
                "the candidate's genuinely relevant experience and skills for a "
                "specific job, reusing the job description's language only where it "
                "truthfully matches something already described elsewhere on the "
                "resume. Do NOT add any skill, credential, employer, or experience "
                "that isn't already present on the resume — only reframe and "
                "re-emphasize what's genuinely there, and keep it roughly the same "
                "length as the original. Do not use em dashes. Respond with JSON only, no prose: "
                '{"tailored_summary": "<rewritten paragraph>"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Full resume (for context — only rewrite the summary below):\n"
                f"{resume_text[:MAX_RESUME_CHARS]}\n\n"
                f"Current summary:\n{original_summary}\n\n"
                f"Job description:\n{jd_text[:MAX_JD_CHARS]}"
            ),
        },
    ]
    result = ai_client.chat_json(messages)
    tailored = result.get("tailored_summary") if isinstance(result, dict) else None
    if not isinstance(tailored, str) or not tailored.strip():
        return []
    tailored_clean = _strip_em_dashes(tailored.strip())
    if tailored_clean == original_summary:
        return []
    return [{"section": "Summary", "original": original_summary, "tailored": tailored_clean}]


MAX_PROJECT_SUGGESTIONS = 3


def generate_gap_flags(jd_text: str, gap_candidates: list[str]) -> list[dict]:
    """Design a small number of consolidated portfolio projects that together cover as
    many genuinely-missing JD skills as possible, rather than one throwaway project per
    skill — a candidate can realistically only build 2-3 projects, so group related
    skills (e.g. a frontend framework + backend framework + database + deployment
    tooling) into the same project wherever that's a coherent, buildable thing."""
    if not gap_candidates:
        return []
    messages = [
        {
            "role": "system",
            "content": (
                "Given a list of skills that are genuinely missing from a candidate's "
                "resume for a specific job, design at most "
                f"{MAX_PROJECT_SUGGESTIONS} concrete, buildable portfolio projects that "
                "TOGETHER cover as many of the listed skills as possible. Group related "
                "skills into the same project wherever it forms a coherent, realistic "
                "build (e.g. one full-stack project can legitimately cover a frontend "
                "framework, a backend framework, a database, and a deployment tool all "
                "at once) — don't force unrelated skills together just to shorten the "
                "list. Every skill in the input list should end up covered by at least "
                "one project if at all feasible.\n\n"
                "For each project, write 2-3 resume-style bullet points describing what "
                "would be built, in the same voice as a real resume bullet: start with a "
                "strong action verb (Built, Implemented, Automated, Integrated, Designed, "
                "...). This project has NOT been built yet, so NEVER invent a specific "
                "number, count, or percentage. Anywhere a finished project's bullet would "
                "normally carry a metric, use a bracketed placeholder instead — [N]+ for "
                "counts, [X]% for percentages, [Y] for other measurements — so the "
                "candidate fills in their own real result once they build and measure it "
                "(e.g. 'automating [N]+ validation scenarios, reducing manual effort by "
                "[X]%'). Do not use em dashes. Respond with JSON only, no prose: "
                '{"projects": [{"title": "...", "covers_skills": ["..."], '
                '"bullets": ["<bullet with [N]/[X] placeholders where a real project would have metrics>", "..."], '
                '"why_valuable": "<1 sentence on why this matters for this job>"}]}'
            ),
        },
        {
            "role": "user",
            "content": f"Job description:\n{jd_text[:MAX_JD_CHARS]}\n\nMissing skills: {gap_candidates}",
        },
    ]
    result = ai_client.chat_json(messages)
    projects = result.get("projects", []) if isinstance(result, dict) else []
    cleaned: list[dict] = []
    for p in projects:
        if (
            not isinstance(p, dict)
            or not p.get("title")
            or not p.get("covers_skills")
            or not isinstance(p.get("bullets"), list)
            or len(p["bullets"]) == 0
            or not p.get("why_valuable")
        ):
            continue
        cleaned.append(
            {
                "title": _strip_em_dashes(p["title"]),
                "covers_skills": p["covers_skills"],
                "bullets": [_strip_em_dashes(b) for b in p["bullets"] if isinstance(b, str)],
                "why_valuable": _strip_em_dashes(p["why_valuable"]),
            }
        )
    return cleaned[:MAX_PROJECT_SUGGESTIONS]


def screen_jd(resume_text: str, jd_text: str) -> dict:
    """Pre-tailoring dealbreaker screen: SKIP is only ever returned with a quoted
    JD sentence that genuinely appears in the JD text — a model claim of SKIP
    without real quoted evidence is dropped back to PASS rather than trusted,
    same grounding-by-verification approach used everywhere else in this app."""
    messages = [
        {
            "role": "system",
            "content": (
                "Screen whether a candidate should bother tailoring their resume for "
                "this job. Flag SKIP ONLY when you can quote the EXACT triggering "
                "sentence from the job description, for one of: no sponsorship now or "
                "in the future / must not require sponsorship / unrestricted work "
                "authorization required; security clearance, US citizenship, or "
                "ITAR/US-persons-only requirement; intern/co-op or 'currently "
                "enrolled/pursuing degree' only; a hard REQUIRED (not preferred) "
                "years-of-experience minimum clearly above what the resume shows; a "
                "PERM-style listing ('Employer will accept... Position requires: "
                "<long tech list>'); or the role's CORE discipline being something "
                "the candidate has no real background in (e.g. low-level/embedded/"
                "kernel/compiler/HPC/FPGA work for a candidate with no such "
                "experience). A missing PREFERRED skill is a gap, not a dealbreaker — "
                "never flag SKIP for that alone. If nothing disqualifying is "
                "quotable, verdict is PASS. Respond with JSON only, no prose: "
                '{"verdict": "PASS" or "SKIP", "skip_reason": "<one sentence, or '
                'null>", "skip_quote": "<exact quoted JD sentence, or null>"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Resume:\n{resume_text[:MAX_RESUME_CHARS]}\n\n"
                f"Job description:\n{jd_text[:MAX_JD_CHARS]}"
            ),
        },
    ]
    result = ai_client.chat_json(messages)
    if not isinstance(result, dict) or result.get("verdict") != "SKIP":
        return {"verdict": "PASS", "skip_reason": None, "skip_quote": None}

    quote = result.get("skip_quote")
    if not isinstance(quote, str) or not quote.strip() or quote.strip() not in jd_text:
        return {"verdict": "PASS", "skip_reason": None, "skip_quote": None}

    reason = result.get("skip_reason")
    return {
        "verdict": "SKIP",
        "skip_reason": _strip_em_dashes(reason) if isinstance(reason, str) else None,
        "skip_quote": quote.strip(),
    }


def compute_fit_verdict(ats_score: int) -> str:
    """Cheap, deterministic categorical read of the numeric score — no extra AI
    call needed since it's a direct function of ats_score's existing bands."""
    if ats_score >= 85:
        return "STRONG MATCH"
    if ats_score >= 65:
        return "SOLID MATCH"
    if ats_score >= 40:
        return "REACH"
    return "WEAK MATCH"


def build_recruiter_note(matched_keywords: list[str], gap_candidates: list[str]) -> str:
    """One-line matched-vs-missing summary, built deterministically from data the
    scoring step already produced — no extra AI call."""
    matched_part = ", ".join(matched_keywords[:6]) if matched_keywords else "none yet"
    missing_part = ", ".join(gap_candidates[:6]) if gap_candidates else "none"
    return f"Keywords matched: {matched_part}. Still genuinely missing: {missing_part}."


@router.post("/analyze", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(ANALYZE_RATE_LIMIT)
def analyze(
    request: Request,
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = (
        db.query(Resume)
        .filter(Resume.id == payload.resume_id, Resume.user_id == current_user.id)
        .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    jd = (
        db.query(JobDescription)
        .filter(JobDescription.id == payload.jd_id, JobDescription.user_id == current_user.id)
        .first()
    )
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    try:
        jd_keywords = extract_jd_keywords(jd.raw_text)
        result = score_resume(jd_keywords, resume.raw_text, embed_fn=ai_client.embed)

        groundable_keywords = [
            kw for kw in result["missing_keywords"] if kw not in result["gap_candidates"]
        ]
        tailored_bullets = generate_tailored_bullets(
            resume.raw_text, groundable_keywords
        ) + generate_summary_tailoring(resume.raw_text, jd.raw_text)
        gap_flags = generate_gap_flags(jd.raw_text, result["gap_candidates"])
        screen_result = screen_jd(resume.raw_text, jd.raw_text)
    except (json.JSONDecodeError, OpenAIError) as exc:
        logger.exception("AI analysis step failed for resume_id=%s jd_id=%s", resume.id, jd.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI analysis step failed (NIM returned an unusable response). Please try again.",
        ) from exc

    screening = {
        **screen_result,
        "fit_verdict": compute_fit_verdict(result["ats_score"]),
        "recruiter_note": build_recruiter_note(result["matched_keywords"], result["gap_candidates"]),
    }

    analysis = Analysis(
        user_id=current_user.id,
        resume_id=resume.id,
        jd_id=jd.id,
        ats_score=result["ats_score"],
        component_breakdown=result["component_breakdown"],
        matched_keywords=result["matched_keywords"],
        missing_keywords=result["missing_keywords"],
        tailored_bullets=tailored_bullets,
        gap_flags=gap_flags,
        formatting_issues=result["formatting_issues"],
        screening=screening,
        confidence=result["confidence"],
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@router.get("/analyses", response_model=list[AnalysisSummary])
def list_analyses(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    rows = (
        db.query(Analysis, Resume.title, JobDescription.title)
        .join(Resume, Analysis.resume_id == Resume.id)
        .join(JobDescription, Analysis.jd_id == JobDescription.id)
        .filter(Analysis.user_id == current_user.id)
        .order_by(Analysis.created_at.desc())
        .all()
    )
    return [
        AnalysisSummary(
            id=a.id,
            resume_id=a.resume_id,
            resume_title=resume_title,
            jd_id=a.jd_id,
            jd_title=jd_title,
            ats_score=a.ats_score,
            created_at=a.created_at,
        )
        for a, resume_title, jd_title in rows
    ]


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = (
        db.query(Analysis)
        .filter(Analysis.id == analysis_id, Analysis.user_id == current_user.id)
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis

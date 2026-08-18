import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAIError
from sqlalchemy.orm import Session

from app import ai_client
from app.database import get_db
from app.deps import get_current_user
from app.models import Analysis, JobDescription, Resume, User
from app.schemas import AnalyzeRequest, AnalysisOut, AnalysisSummary
from app.scoring import score_resume

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analyze"])

MAX_TAILORED_BULLETS = 6
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
    messages = [
        {
            "role": "system",
            "content": (
                "You tailor resume bullets to naturally incorporate specific keywords, "
                "without keyword stuffing and without ever fabricating experience. Only "
                "rewrite a bullet if the keyword can be truthfully grounded in what it "
                "already describes. Respond with JSON only, no prose: "
                '{"bullets": [{"section": "<section name or \'Experience\'>", '
                '"original": "<verbatim line copied exactly from the resume>", '
                '"tailored": "<rewritten line>"}]}. '
                f"Include at most {MAX_TAILORED_BULLETS} bullets. If a keyword cannot be "
                "naturally grounded in any existing bullet, omit it entirely — never invent "
                "new experience, employers, tools, or metrics."
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
    return [
        b
        for b in bullets
        if isinstance(b, dict)
        and b.get("original")
        and b.get("tailored")
        and b["original"] != b["tailored"]
        and b["original"] in resume_text  # enforce real grounding, not just non-empty
    ][:MAX_TAILORED_BULLETS]


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
                "[X]%'). Respond with JSON only, no prose: "
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
    return [
        p
        for p in projects
        if isinstance(p, dict)
        and p.get("title")
        and p.get("covers_skills")
        and isinstance(p.get("bullets"), list)
        and len(p["bullets"]) > 0
        and p.get("why_valuable")
    ][:MAX_PROJECT_SUGGESTIONS]


@router.post("/analyze", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
def analyze(
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
        tailored_bullets = generate_tailored_bullets(resume.raw_text, groundable_keywords)
        gap_flags = generate_gap_flags(jd.raw_text, result["gap_candidates"])
    except (json.JSONDecodeError, OpenAIError) as exc:
        logger.exception("AI analysis step failed for resume_id=%s jd_id=%s", resume.id, jd.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI analysis step failed (NIM returned an unusable response). Please try again.",
        ) from exc

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

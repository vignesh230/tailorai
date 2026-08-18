from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import ai_client
from app.database import get_db
from app.deps import get_current_user
from app.models import Analysis, JobDescription, Resume, User
from app.schemas import AnalyzeRequest, AnalysisOut
from app.scoring import score_resume

router = APIRouter(tags=["analyze"])

MAX_TAILORED_BULLETS = 6
MAX_GAP_FLAGS = 5


def extract_jd_keywords(jd_text: str) -> list[str]:
    messages = [
        {
            "role": "system",
            "content": (
                "You extract required skills and keywords from job descriptions. "
                "Respond with JSON only, no prose: {\"keywords\": [\"...\"]}. "
                "Include concrete skills, tools, technologies, certifications, and "
                "role-specific requirements (10-25 items). Skip generic filler like "
                "'team player' or 'good communicator'."
            ),
        },
        {"role": "user", "content": jd_text},
    ]
    result = ai_client.chat_json(messages)
    keywords = result.get("keywords", []) if isinstance(result, dict) else []
    return [k.strip() for k in keywords if isinstance(k, str) and k.strip()]


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
                f"Resume:\n{resume_text}\n\n"
                f"Keywords to naturally incorporate where truthful: {groundable_keywords}"
            ),
        },
    ]
    result = ai_client.chat_json(messages)
    bullets = result.get("bullets", []) if isinstance(result, dict) else []
    return [
        b
        for b in bullets
        if isinstance(b, dict) and b.get("original") and b.get("tailored")
    ][:MAX_TAILORED_BULLETS]


def generate_gap_flags(jd_text: str, gap_candidates: list[str]) -> list[dict]:
    if not gap_candidates:
        return []
    candidates = gap_candidates[:MAX_GAP_FLAGS]
    messages = [
        {
            "role": "system",
            "content": (
                "For each listed skill that is genuinely missing from a candidate's resume, "
                "suggest ONE concrete, buildable sample/portfolio project that would best "
                "demonstrate that skill, and a one-sentence reason it matters for this "
                "specific job description. Respond with JSON only, no prose: "
                '{"gaps": [{"skill": "...", "suggested_project": "...", "why_valuable": "..."}]}'
            ),
        },
        {
            "role": "user",
            "content": f"Job description:\n{jd_text}\n\nMissing skills: {candidates}",
        },
    ]
    result = ai_client.chat_json(messages)
    gaps = result.get("gaps", []) if isinstance(result, dict) else []
    return [
        g
        for g in gaps
        if isinstance(g, dict) and g.get("skill") and g.get("suggested_project") and g.get("why_valuable")
    ]


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

    jd_keywords = extract_jd_keywords(jd.raw_text)
    result = score_resume(jd_keywords, resume.raw_text, embed_fn=ai_client.embed)

    groundable_keywords = [
        kw for kw in result["missing_keywords"] if kw not in result["gap_candidates"]
    ]
    tailored_bullets = generate_tailored_bullets(resume.raw_text, groundable_keywords)
    gap_flags = generate_gap_flags(jd.raw_text, result["gap_candidates"])

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

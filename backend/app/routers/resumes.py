from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session
import io

from app.database import get_db
from app.deps import get_current_user
from app.models import Resume, User
from app.schemas import ResumeCreate, ResumeOut, ResumeParseOut

router = APIRouter(prefix="/resumes", tags=["resumes"])

MAX_PDF_BYTES = 5 * 1024 * 1024  # 5MB


@router.post("/parse-pdf", response_model=ResumeParseOut)
async def parse_resume_pdf(
    file: UploadFile, current_user: User = Depends(get_current_user)
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    contents = await file.read()
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="PDF must be smaller than 5MB")

    try:
        reader = PdfReader(io.BytesIO(contents))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except PdfReadError:
        raise HTTPException(status_code=400, detail="Could not read this PDF — it may be corrupted or encrypted")

    if not text:
        raise HTTPException(
            status_code=400,
            detail="No extractable text found in this PDF (it may be a scanned image)",
        )

    return ResumeParseOut(raw_text=text)


@router.post("", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
def create_resume(
    payload: ResumeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = Resume(user_id=current_user.id, title=payload.title, raw_text=payload.raw_text)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("", response_model=list[ResumeOut])
def list_resumes(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return (
        db.query(Resume)
        .filter(Resume.user_id == current_user.id)
        .order_by(Resume.created_at.desc())
        .all()
    )


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.user_id == current_user.id)
        .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume

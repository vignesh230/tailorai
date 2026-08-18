from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import JobDescription, User
from app.schemas import JobDescriptionCreate, JobDescriptionOut

router = APIRouter(prefix="/job-descriptions", tags=["job_descriptions"])


@router.post("", response_model=JobDescriptionOut, status_code=status.HTTP_201_CREATED)
def create_jd(
    payload: JobDescriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jd = JobDescription(user_id=current_user.id, title=payload.title, raw_text=payload.raw_text)
    db.add(jd)
    db.commit()
    db.refresh(jd)
    return jd


@router.get("", response_model=list[JobDescriptionOut])
def list_jds(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return (
        db.query(JobDescription)
        .filter(JobDescription.user_id == current_user.id)
        .order_by(JobDescription.created_at.desc())
        .all()
    )


@router.get("/{jd_id}", response_model=JobDescriptionOut)
def get_jd(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jd = (
        db.query(JobDescription)
        .filter(JobDescription.id == jd_id, JobDescription.user_id == current_user.id)
        .first()
    )
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    return jd

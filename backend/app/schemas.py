from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ResumeCreate(BaseModel):
    title: str
    raw_text: str


class ResumeParseOut(BaseModel):
    raw_text: str


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    raw_text: str
    created_at: datetime


class JobDescriptionCreate(BaseModel):
    title: str
    raw_text: str


class JobDescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    raw_text: str
    created_at: datetime


class AnalyzeRequest(BaseModel):
    resume_id: int
    jd_id: int


class TailoredBullet(BaseModel):
    section: str
    original: str
    tailored: str


class GapFlag(BaseModel):
    skill: str
    suggested_project: str
    why_valuable: str


class ComponentBreakdown(BaseModel):
    keyword_score: float
    semantic_score: float
    formatting_score: float
    keyword_weight: float
    semantic_weight: float
    formatting_weight: float


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resume_id: int
    jd_id: int
    ats_score: int
    component_breakdown: ComponentBreakdown
    matched_keywords: list[str]
    missing_keywords: list[str]
    tailored_bullets: list[TailoredBullet]
    gap_flags: list[GapFlag]
    formatting_issues: list[str]
    created_at: datetime

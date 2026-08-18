const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "tailorai_token";

export interface Resume {
  id: number;
  title: string;
  raw_text: string;
  created_at: string;
}

export interface JobDescription {
  id: number;
  title: string;
  raw_text: string;
  created_at: string;
}

export interface TailoredBullet {
  section: string;
  original: string;
  tailored: string;
}

export interface ProjectSuggestion {
  title: string;
  covers_skills: string[];
  bullets: string[];
  why_valuable: string;
}

export interface ComponentBreakdown {
  keyword_score: number;
  semantic_score: number;
  formatting_score: number;
  keyword_weight: number;
  semantic_weight: number;
  formatting_weight: number;
}

export interface Screening {
  verdict: "PASS" | "SKIP";
  skip_reason: string | null;
  skip_quote: string | null;
  fit_verdict: "STRONG MATCH" | "SOLID MATCH" | "REACH" | "WEAK MATCH";
  recruiter_note: string;
}

export interface Analysis {
  id: number;
  resume_id: number;
  jd_id: number;
  ats_score: number;
  component_breakdown: ComponentBreakdown;
  matched_keywords: string[];
  missing_keywords: string[];
  tailored_bullets: TailoredBullet[];
  gap_flags: ProjectSuggestion[];
  formatting_issues: string[];
  screening: Screening;
  created_at: string;
}

export interface AnalysisSummary {
  id: number;
  resume_id: number;
  resume_title: string;
  jd_id: number;
  jd_title: string;
  ats_score: number;
  created_at: string;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (!(options.body instanceof URLSearchParams) && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function signup(email: string, password: string) {
  return request("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const data = await request<{ access_token: string }>("/auth/login", {
    method: "POST",
    body,
  });
  setToken(data.access_token);
  return data.access_token;
}

export async function me() {
  return request("/auth/me");
}

export async function listResumes(): Promise<Resume[]> {
  return request("/resumes");
}

export async function createResume(title: string, raw_text: string): Promise<Resume> {
  return request("/resumes", { method: "POST", body: JSON.stringify({ title, raw_text }) });
}

export async function parseResumePdf(file: File): Promise<{ raw_text: string }> {
  const formData = new FormData();
  formData.append("file", file);
  return request("/resumes/parse-pdf", { method: "POST", body: formData });
}

export async function listJobDescriptions(): Promise<JobDescription[]> {
  return request("/job-descriptions");
}

export async function createJobDescription(title: string, raw_text: string): Promise<JobDescription> {
  return request("/job-descriptions", { method: "POST", body: JSON.stringify({ title, raw_text }) });
}

export async function analyze(resume_id: number, jd_id: number): Promise<Analysis> {
  return request("/analyze", { method: "POST", body: JSON.stringify({ resume_id, jd_id }) });
}

export async function listAnalyses(): Promise<AnalysisSummary[]> {
  return request("/analyses");
}

export async function getAnalysis(id: number | string): Promise<Analysis> {
  return request(`/analyses/${id}`);
}

export async function getResume(id: number): Promise<Resume> {
  return request(`/resumes/${id}`);
}

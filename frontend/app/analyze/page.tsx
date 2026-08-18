"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { analyze, createJobDescription, createResume, parseResumePdf } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  assembleResumeText,
  emptyEducation,
  emptyExperience,
  emptyResumeForm,
  ResumeFormData,
} from "@/lib/resumeForm";

type ResumeInputMode = "paste" | "pdf" | "form";

export default function AnalyzePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [resumeMode, setResumeMode] = useState<ResumeInputMode>("paste");
  const [resumeTitle, setResumeTitle] = useState("My Resume");
  const [resumeText, setResumeText] = useState("");
  const [resumeForm, setResumeForm] = useState<ResumeFormData>(emptyResumeForm());
  const [pdfParsing, setPdfParsing] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [jdTitle, setJdTitle] = useState("Target Role");
  const [jdText, setJdText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (resumeMode === "form") setResumeText(assembleResumeText(resumeForm));
  }, [resumeMode, resumeForm]);

  async function handlePdfChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPdfError(null);
    setPdfParsing(true);
    try {
      const { raw_text } = await parseResumePdf(file);
      setResumeText(raw_text);
      if (!resumeTitle || resumeTitle === "My Resume") {
        setResumeTitle(file.name.replace(/\.pdf$/i, ""));
      }
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "Could not parse this PDF");
    } finally {
      setPdfParsing(false);
    }
  }

  function updateExperience(index: number, patch: Partial<ResumeFormData["experience"][number]>) {
    setResumeForm((f) => ({
      ...f,
      experience: f.experience.map((exp, i) => (i === index ? { ...exp, ...patch } : exp)),
    }));
  }

  function updateEducation(index: number, patch: Partial<ResumeFormData["education"][number]>) {
    setResumeForm((f) => ({
      ...f,
      education: f.education.map((edu, i) => (i === index ? { ...edu, ...patch } : edu)),
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!resumeText.trim()) {
      setError("Add your resume text — paste it, upload a PDF, or fill in the details form.");
      return;
    }
    setSubmitting(true);
    try {
      const resume = await createResume(resumeTitle, resumeText);
      const jd = await createJobDescription(jdTitle, jdText);
      const result = await analyze(resume.id, jd.id);
      sessionStorage.setItem(
        `tailorai_analysis_${result.id}`,
        JSON.stringify({ analysis: result, resumeText })
      );
      router.push(`/results/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      setSubmitting(false);
    }
  }

  if (loading || !user) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="mb-1 text-2xl font-semibold">New analysis</h1>
      <p className="mb-8 text-sm text-slate-500">
        Paste your resume and the job description you're targeting.
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-8">
        <div className="flex flex-col gap-3">
          <label className="text-sm font-medium">Resume title</label>
          <input
            value={resumeTitle}
            onChange={(e) => setResumeTitle(e.target.value)}
            required
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />

          <div className="flex gap-1 rounded-md bg-slate-100 p-1 text-sm">
            {(["paste", "pdf", "form"] as ResumeInputMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setResumeMode(mode)}
                className={`flex-1 rounded px-3 py-1.5 font-medium ${
                  resumeMode === mode ? "bg-white shadow-sm" : "text-slate-500"
                }`}
              >
                {mode === "paste" ? "Paste text" : mode === "pdf" ? "Upload PDF" : "Fill in details"}
              </button>
            ))}
          </div>

          {resumeMode === "paste" && (
            <textarea
              value={resumeText}
              onChange={(e) => setResumeText(e.target.value)}
              required
              rows={12}
              placeholder="Paste your resume text here..."
              className="rounded-md border border-slate-300 px-3 py-2 font-mono text-xs"
            />
          )}

          {resumeMode === "pdf" && (
            <div className="flex flex-col gap-2">
              <input
                type="file"
                accept="application/pdf"
                onChange={handlePdfChange}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              {pdfParsing && <p className="text-sm text-slate-500">Extracting text...</p>}
              {pdfError && <p className="text-sm text-red-600">{pdfError}</p>}
              {resumeText && !pdfParsing && (
                <>
                  <label className="text-sm font-medium">Extracted text (edit if needed)</label>
                  <textarea
                    value={resumeText}
                    onChange={(e) => setResumeText(e.target.value)}
                    rows={10}
                    className="rounded-md border border-slate-300 px-3 py-2 font-mono text-xs"
                  />
                </>
              )}
            </div>
          )}

          {resumeMode === "form" && (
            <div className="flex flex-col gap-4 rounded-md border border-slate-200 p-4">
              <div className="grid grid-cols-2 gap-3">
                <input
                  placeholder="Full name"
                  value={resumeForm.fullName}
                  onChange={(e) => setResumeForm((f) => ({ ...f, fullName: e.target.value }))}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
                <input
                  placeholder="Email / phone / location"
                  value={resumeForm.contact}
                  onChange={(e) => setResumeForm((f) => ({ ...f, contact: e.target.value }))}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
              <textarea
                placeholder="Summary (optional)"
                value={resumeForm.summary}
                onChange={(e) => setResumeForm((f) => ({ ...f, summary: e.target.value }))}
                rows={2}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />

              <div>
                <p className="mb-2 text-sm font-semibold">Experience</p>
                <div className="flex flex-col gap-3">
                  {resumeForm.experience.map((exp, i) => (
                    <div key={i} className="rounded-md border border-slate-200 p-3">
                      <div className="mb-2 grid grid-cols-3 gap-2">
                        <input
                          placeholder="Title"
                          value={exp.title}
                          onChange={(e) => updateExperience(i, { title: e.target.value })}
                          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                        />
                        <input
                          placeholder="Company"
                          value={exp.company}
                          onChange={(e) => updateExperience(i, { company: e.target.value })}
                          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                        />
                        <input
                          placeholder="Dates"
                          value={exp.dates}
                          onChange={(e) => updateExperience(i, { dates: e.target.value })}
                          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                        />
                      </div>
                      <textarea
                        placeholder="Bullet points, one per line"
                        value={exp.bullets}
                        onChange={(e) => updateExperience(i, { bullets: e.target.value })}
                        rows={3}
                        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                      />
                      {resumeForm.experience.length > 1 && (
                        <button
                          type="button"
                          onClick={() =>
                            setResumeForm((f) => ({
                              ...f,
                              experience: f.experience.filter((_, idx) => idx !== i),
                            }))
                          }
                          className="mt-1 text-xs text-red-600"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      setResumeForm((f) => ({ ...f, experience: [...f.experience, emptyExperience()] }))
                    }
                    className="self-start text-sm font-medium text-slate-900 underline"
                  >
                    + Add experience
                  </button>
                </div>
              </div>

              <div>
                <p className="mb-2 text-sm font-semibold">Education</p>
                <div className="flex flex-col gap-3">
                  {resumeForm.education.map((edu, i) => (
                    <div key={i} className="grid grid-cols-3 gap-2">
                      <input
                        placeholder="Degree"
                        value={edu.degree}
                        onChange={(e) => updateEducation(i, { degree: e.target.value })}
                        className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                      />
                      <input
                        placeholder="School"
                        value={edu.school}
                        onChange={(e) => updateEducation(i, { school: e.target.value })}
                        className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                      />
                      <input
                        placeholder="Dates"
                        value={edu.dates}
                        onChange={(e) => updateEducation(i, { dates: e.target.value })}
                        className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                      />
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      setResumeForm((f) => ({ ...f, education: [...f.education, emptyEducation()] }))
                    }
                    className="self-start text-sm font-medium text-slate-900 underline"
                  >
                    + Add education
                  </button>
                </div>
              </div>

              <input
                placeholder="Skills (comma-separated)"
                value={resumeForm.skills}
                onChange={(e) => setResumeForm((f) => ({ ...f, skills: e.target.value }))}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />

              <details className="text-xs text-slate-500">
                <summary className="cursor-pointer select-none">Preview assembled resume text</summary>
                <pre className="mt-2 whitespace-pre-wrap rounded-md bg-slate-50 p-3">{resumeText}</pre>
              </details>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium">Job title</label>
          <input
            value={jdTitle}
            onChange={(e) => setJdTitle(e.target.value)}
            required
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <label className="text-sm font-medium">Job description text</label>
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            required
            rows={12}
            placeholder="Paste the job description here..."
            className="rounded-md border border-slate-300 px-3 py-2 font-mono text-xs"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {submitting ? "Analyzing... (can take up to a minute)" : "Analyze"}
        </button>
      </form>
    </main>
  );
}

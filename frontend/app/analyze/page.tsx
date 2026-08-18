"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { analyze, createJobDescription, createResume } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AnalyzePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [resumeTitle, setResumeTitle] = useState("My Resume");
  const [resumeText, setResumeText] = useState("");
  const [jdTitle, setJdTitle] = useState("Target Role");
  const [jdText, setJdText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
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
        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium">Resume title</label>
          <input
            value={resumeTitle}
            onChange={(e) => setResumeTitle(e.target.value)}
            required
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <label className="text-sm font-medium">Resume text</label>
          <textarea
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            required
            rows={12}
            placeholder="Paste your resume text here..."
            className="rounded-md border border-slate-300 px-3 py-2 font-mono text-xs"
          />
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

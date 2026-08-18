"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Analysis } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { buildTailoredResumeText, downloadPdf, downloadWord } from "@/lib/export";

interface StoredAnalysis {
  analysis: Analysis;
  resumeText: string;
}

function scoreColor(score: number) {
  if (score >= 75) return "text-green-600";
  if (score >= 50) return "text-amber-600";
  return "text-red-600";
}

export default function ResultsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<StoredAnalysis | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [selectedGaps, setSelectedGaps] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
      return;
    }
    const raw = sessionStorage.getItem(`tailorai_analysis_${params.id}`);
    if (raw) {
      setData(JSON.parse(raw));
    } else {
      setNotFound(true);
    }
  }, [loading, user, router, params.id]);

  if (loading || !user) return null;

  if (notFound) {
    return (
      <main className="mx-auto max-w-xl px-4 py-10 text-center">
        <p className="mb-4 text-sm text-slate-500">
          This result isn&apos;t available in this browser session anymore.
        </p>
        <Link href="/analyze" className="text-sm font-medium text-slate-900 underline">
          Start a new analysis
        </Link>
      </main>
    );
  }

  if (!data) return null;

  const { analysis, resumeText } = data;
  const { component_breakdown: cb } = analysis;

  const selectedProjects = analysis.gap_flags.filter((g) => selectedGaps.has(g.skill));
  const tailoredResumeText = useMemo(
    () => buildTailoredResumeText(resumeText, analysis.tailored_bullets, selectedProjects),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [resumeText, analysis.tailored_bullets, selectedGaps]
  );

  function toggleGap(skill: string) {
    setSelectedGaps((prev) => {
      const next = new Set(prev);
      if (next.has(skill)) next.delete(skill);
      else next.add(skill);
      return next;
    });
  }

  function handleDownloadPdf() {
    downloadPdf("tailored-resume.pdf", tailoredResumeText);
  }

  function handleDownloadWord() {
    downloadWord("tailored-resume.doc", tailoredResumeText);
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Results</h1>
        <Link href="/dashboard" className="text-sm text-slate-500 underline">
          Back to dashboard
        </Link>
      </div>

      <section className="mb-8 rounded-lg border border-slate-200 bg-white p-6">
        <p className="text-sm text-slate-500">ATS Score</p>
        <p className={`text-5xl font-bold ${scoreColor(analysis.ats_score)}`}>
          {analysis.ats_score}
          <span className="text-xl text-slate-400">/100</span>
        </p>

        <div className="mt-6 grid grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-slate-500">Keyword coverage ({Math.round(cb.keyword_weight * 100)}%)</p>
            <p className="text-lg font-semibold">{cb.keyword_score.toFixed(0)}</p>
          </div>
          <div>
            <p className="text-slate-500">Semantic coverage ({Math.round(cb.semantic_weight * 100)}%)</p>
            <p className="text-lg font-semibold">{cb.semantic_score.toFixed(0)}</p>
          </div>
          <div>
            <p className="text-slate-500">Formatting ({Math.round(cb.formatting_weight * 100)}%)</p>
            <p className="text-lg font-semibold">{cb.formatting_score.toFixed(0)}</p>
          </div>
        </div>
      </section>

      <section className="mb-8 rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Your tailored resume
          </h2>
          <div className="flex gap-3">
            <button onClick={handleDownloadPdf} className="text-sm font-medium text-slate-900 underline">
              Download PDF
            </button>
            <button onClick={handleDownloadWord} className="text-sm font-medium text-slate-900 underline">
              Download Word
            </button>
          </div>
        </div>
        <p className="mb-3 text-xs text-slate-500">
          Groundable bullets are already rewritten in place below. Check any suggested projects
          further down the page to add them here too — nothing is added unless you pick it.
        </p>
        <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md bg-slate-50 p-4 font-mono text-xs">
          {tailoredResumeText}
        </pre>
      </section>

      <section className="mb-8 grid gap-6 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Matched keywords
          </h2>
          <div className="flex flex-wrap gap-2">
            {analysis.matched_keywords.map((k) => (
              <span key={k} className="rounded-full bg-green-100 px-3 py-1 text-xs text-green-800">
                {k}
              </span>
            ))}
            {analysis.matched_keywords.length === 0 && (
              <p className="text-sm text-slate-400">None matched.</p>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Missing keywords
          </h2>
          <div className="flex flex-wrap gap-2">
            {analysis.missing_keywords.map((k) => (
              <span key={k} className="rounded-full bg-red-100 px-3 py-1 text-xs text-red-800">
                {k}
              </span>
            ))}
            {analysis.missing_keywords.length === 0 && (
              <p className="text-sm text-slate-400">None missing — great coverage.</p>
            )}
          </div>
        </div>
      </section>

      {analysis.formatting_issues.length > 0 && (
        <section className="mb-8 rounded-lg border border-amber-200 bg-amber-50 p-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-amber-800">
            Formatting issues
          </h2>
          <ul className="list-disc space-y-1 pl-5 text-sm text-amber-900">
            {analysis.formatting_issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="mb-8 rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Tailored bullet suggestions
        </h2>
        {analysis.tailored_bullets.length === 0 ? (
          <p className="text-sm text-slate-400">
            No bullets needed rewriting — your resume already covers the groundable keywords.
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {analysis.tailored_bullets.map((b, i) => (
              <li key={i} className="text-sm">
                <p className="mb-1 text-xs font-semibold uppercase text-slate-400">{b.section}</p>
                <p className="text-slate-400 line-through">{b.original}</p>
                <p className="text-slate-900">{b.tailored}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-8 rounded-lg border border-red-200 bg-red-50 p-6">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-red-800">
          Honest gaps — genuinely missing skills
        </h2>
        {analysis.gap_flags.length === 0 ? (
          <p className="text-sm text-red-700">
            No genuine skill gaps detected against this job description.
          </p>
        ) : (
          <>
            <p className="mb-3 text-xs text-red-700">
              These skills aren&apos;t in your resume at all — nothing was fabricated. Check any
              you&apos;d like to add a project for; it'll appear in the tailored resume above.
            </p>
            <ul className="flex flex-col gap-3">
              {analysis.gap_flags.map((g) => (
                <li key={g.skill} className="flex gap-3 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedGaps.has(g.skill)}
                    onChange={() => toggleGap(g.skill)}
                    className="mt-1 h-4 w-4 flex-shrink-0"
                  />
                  <div>
                    <p className="font-semibold text-red-900">{g.skill}</p>
                    <p className="text-red-800">Suggested project: {g.suggested_project}</p>
                    <p className="text-red-700">{g.why_valuable}</p>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="flex gap-3">
        <button
          onClick={handleDownloadPdf}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          Download tailored resume (PDF)
        </button>
        <button
          onClick={handleDownloadWord}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-900"
        >
          Download tailored resume (Word)
        </button>
      </section>
    </main>
  );
}

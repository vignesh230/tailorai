"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Analysis, analyze, createResume, getAnalysis, getResume } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  buildTailoredResumeText,
  downloadLatex,
  downloadPdf,
  downloadWord,
  replaceProjectsSection,
} from "@/lib/export";

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
  // The editable draft the user reviews and tweaks before downloading — this is
  // the single source of truth for what actually gets exported.
  const [resumeDraft, setResumeDraft] = useState("");
  const [reanalyzing, setReanalyzing] = useState(false);
  const [reanalyzeError, setReanalyzeError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
      return;
    }
    if (loading) return;

    function applyData(parsed: StoredAnalysis) {
      setData(parsed);
      setResumeDraft(buildTailoredResumeText(parsed.resumeText, parsed.analysis.tailored_bullets));
    }

    const raw = sessionStorage.getItem(`tailorai_analysis_${params.id}`);
    if (raw) {
      applyData(JSON.parse(raw));
      return;
    }

    // Not in this tab's session (revisited later, opened in a new tab, or
    // reached from the dashboard's analysis history) — fetch from the backend.
    getAnalysis(params.id)
      .then(async (analysis) => {
        const resume = await getResume(analysis.resume_id);
        const parsed = { analysis, resumeText: resume.raw_text };
        sessionStorage.setItem(`tailorai_analysis_${params.id}`, JSON.stringify(parsed));
        applyData(parsed);
      })
      .catch(() => setNotFound(true));
  }, [loading, user, router, params.id]);

  if (loading || !user) return null;

  if (notFound) {
    return (
      <main className="mx-auto max-w-xl px-4 py-10 text-center">
        <p className="mb-4 text-sm text-slate-500">
          This analysis doesn&apos;t exist or doesn&apos;t belong to your account.
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

  function toggleGap(title: string) {
    setSelectedGaps((prev) => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);

      const nextProjects = analysis.gap_flags.filter((g) => next.has(g.title));
      setResumeDraft((prevDraft) => replaceProjectsSection(prevDraft, nextProjects));

      return next;
    });
  }

  function resetDraft() {
    const selectedProjects = analysis.gap_flags.filter((g) => selectedGaps.has(g.title));
    setResumeDraft(buildTailoredResumeText(resumeText, analysis.tailored_bullets, selectedProjects));
  }

  function handleDownloadPdf() {
    downloadPdf("tailored-resume.pdf", resumeDraft);
  }

  function handleDownloadWord() {
    downloadWord("tailored-resume.doc", resumeDraft);
  }

  function handleDownloadLatex() {
    downloadLatex("tailored-resume.tex", resumeDraft);
  }

  async function handleReanalyze() {
    setReanalyzeError(null);
    setReanalyzing(true);
    try {
      const newResume = await createResume("Tailored Resume", resumeDraft);
      const result = await analyze(newResume.id, analysis.jd_id);
      sessionStorage.setItem(
        `tailorai_analysis_${result.id}`,
        JSON.stringify({ analysis: result, resumeText: resumeDraft })
      );
      router.push(`/results/${result.id}`);
    } catch (err) {
      setReanalyzeError(err instanceof Error ? err.message : "Re-analysis failed");
      setReanalyzing(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Results</h1>
        <Link href="/dashboard" className="text-sm text-slate-500 underline">
          Back to dashboard
        </Link>
      </div>

      {analysis.screening.verdict === "SKIP" && (
        <section className="mb-8 rounded-lg border border-amber-300 bg-amber-50 p-6">
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-amber-900">
            Possible dealbreaker before you spend time tailoring
          </h2>
          <p className="text-sm text-amber-900">{analysis.screening.skip_reason}</p>
          <p className="mt-2 border-l-2 border-amber-400 pl-3 text-sm italic text-amber-800">
            &ldquo;{analysis.screening.skip_quote}&rdquo;
          </p>
          <p className="mt-2 text-xs text-amber-700">
            Quoted directly from the job description below — the results below still work if
            you want to tailor anyway.
          </p>
        </section>
      )}

      <section className="mb-8 rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-slate-500">ATS Score</p>
            <p className={`text-5xl font-bold ${scoreColor(analysis.ats_score)}`}>
              {analysis.ats_score}
              <span className="text-xl text-slate-400">/100</span>
            </p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-700">
            {analysis.screening.fit_verdict}
          </span>
        </div>
        <p className="mt-3 text-sm text-slate-600">{analysis.screening.recruiter_note}</p>

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

      {/* Side by side: the resume draft stays pinned on the left while you check
          suggested projects on the right, so the update is visible immediately
          without scrolling back and forth. */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2 lg:items-start">
        <div className="lg:sticky lg:top-6">
          <section className="rounded-lg border border-slate-200 bg-white p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                Your tailored resume
              </h2>
              <div className="flex flex-wrap gap-3">
                <button onClick={resetDraft} className="text-sm text-slate-500 underline">
                  Reset to AI suggestion
                </button>
                <button onClick={handleDownloadPdf} className="text-sm font-medium text-slate-900 underline">
                  Download PDF
                </button>
                <button onClick={handleDownloadWord} className="text-sm font-medium text-slate-900 underline">
                  Download Word
                </button>
                <button onClick={handleDownloadLatex} className="text-sm font-medium text-slate-900 underline">
                  Download LaTeX
                </button>
              </div>
            </div>
            <p className="mb-3 text-xs text-slate-500">
              This is exactly what gets downloaded — edit it directly, or check suggested
              projects on the right to add them here (nothing is added unless you pick it).
              PDF/Word/LaTeX are all rendered from this text with proper section formatting,
              not a plain text dump.
            </p>
            <textarea
              value={resumeDraft}
              onChange={(e) => setResumeDraft(e.target.value)}
              rows={26}
              className="w-full whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-4 font-mono text-xs"
            />
            <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-4">
              <button
                onClick={handleReanalyze}
                disabled={reanalyzing}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {reanalyzing ? "Re-analyzing..." : "Re-analyze with these changes"}
              </button>
              <p className="text-xs text-slate-500">
                See your real, recalculated ATS score for the resume as edited above.
              </p>
            </div>
            {reanalyzeError && <p className="mt-2 text-sm text-red-600">{reanalyzeError}</p>}
          </section>
        </div>

        <div className="flex flex-col gap-8">
          <section className="grid gap-6 sm:grid-cols-2">
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
            <section className="rounded-lg border border-amber-200 bg-amber-50 p-6">
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

          <section className="rounded-lg border border-slate-200 bg-white p-6">
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

          <section className="rounded-lg border border-red-200 bg-red-50 p-6">
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
                  None of these skills are in your resume — nothing was fabricated. These{" "}
                  {analysis.gap_flags.length} project{analysis.gap_flags.length > 1 ? "s" : ""}{" "}
                  together cover every missing skill above. Checking one <strong>replaces</strong>{" "}
                  your resume&apos;s Projects section (see it update on the left) with the
                  checked suggestions — your original projects are still in the &quot;Reset to
                  AI suggestion&quot; version if you want them back. Bullets use [N]/[X]
                  placeholders instead of invented numbers — fill in your real results once
                  you&apos;ve actually built and measured each one.
                </p>
                <ul className="flex flex-col gap-4">
                  {analysis.gap_flags.map((g) => (
                    <li key={g.title} className="flex gap-3 text-sm">
                      <input
                        type="checkbox"
                        checked={selectedGaps.has(g.title)}
                        onChange={() => toggleGap(g.title)}
                        className="mt-1 h-4 w-4 flex-shrink-0"
                      />
                      <div>
                        <p className="font-semibold text-red-900">{g.title}</p>
                        <div className="my-1 flex flex-wrap gap-1">
                          {g.covers_skills.map((skill) => (
                            <span
                              key={skill}
                              className="rounded-full bg-red-200 px-2 py-0.5 text-xs text-red-900"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                        <ul className="list-disc pl-5 text-red-800">
                          {g.bullets.map((bullet, i) => (
                            <li key={i}>{bullet}</li>
                          ))}
                        </ul>
                        <p className="mt-1 text-red-700">{g.why_valuable}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AnalysisSummary,
  JobDescription,
  Resume,
  listAnalyses,
  listJobDescriptions,
  listResumes,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

function scoreColor(score: number) {
  if (score >= 75) return "text-green-600";
  if (score >= 50) return "text-amber-600";
  return "text-red-600";
}

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [jds, setJds] = useState<JobDescription[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [loadingLists, setLoadingLists] = useState(true);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    Promise.all([listResumes(), listJobDescriptions(), listAnalyses()])
      .then(([r, j, a]) => {
        setResumes(r);
        setJds(j);
        setAnalyses(a);
      })
      .finally(() => setLoadingLists(false));
  }, [loading, user, router]);

  if (loading || !user) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">TailorAI</h1>
          <p className="text-sm text-slate-500">Signed in as {user.email}</p>
        </div>
        <button onClick={logout} className="text-sm text-slate-500 underline">
          Log out
        </button>
      </div>

      <Link
        href="/analyze"
        className="mb-10 inline-block rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white"
      >
        + New analysis
      </Link>

      {loadingLists ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : (
        <>
        <section className="mb-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Past analyses
          </h2>
          {analyses.length === 0 ? (
            <p className="text-sm text-slate-400">No analyses yet — run one above.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {analyses.map((a) => (
                <li key={a.id}>
                  <Link
                    href={`/results/${a.id}`}
                    className="flex items-center justify-between rounded-md border border-slate-200 bg-white p-3 hover:border-slate-300"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        {a.resume_title} <span className="text-slate-400">vs</span> {a.jd_title}
                      </p>
                      <p className="text-xs text-slate-400">
                        {new Date(a.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <p className={`text-lg font-bold ${scoreColor(a.ats_score)}`}>{a.ats_score}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="grid gap-8 sm:grid-cols-2">
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Resumes
            </h2>
            {resumes.length === 0 && (
              <p className="text-sm text-slate-400">No resumes yet.</p>
            )}
            <ul className="flex flex-col gap-2">
              {resumes.map((r) => (
                <li key={r.id} className="rounded-md border border-slate-200 bg-white p-3">
                  <p className="text-sm font-medium">{r.title}</p>
                  <p className="text-xs text-slate-400">
                    {new Date(r.created_at).toLocaleDateString()}
                  </p>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Job descriptions
            </h2>
            {jds.length === 0 && (
              <p className="text-sm text-slate-400">No job descriptions yet.</p>
            )}
            <ul className="flex flex-col gap-2">
              {jds.map((j) => (
                <li key={j.id} className="rounded-md border border-slate-200 bg-white p-3">
                  <p className="text-sm font-medium">{j.title}</p>
                  <p className="text-xs text-slate-400">
                    {new Date(j.created_at).toLocaleDateString()}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        </div>
        </>
      )}
    </main>
  );
}

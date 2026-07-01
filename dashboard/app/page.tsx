"use client";

import { useState } from "react";
import { useRun } from "@/components/DashboardShell";
import MetricCard from "@/components/MetricCard";

interface Summary {
  pipeline_run: string;
  total_resumes: number;
  total_selected: number;
  total_rejected: number;
  top_score: number | null;
  bottom_selected_score: number | null;
}

interface Department {
  department: string;
  score: number;
  experience?: number;
  projects?: number;
  learning_potential?: number;
  reasoning?: string;
}

interface Candidate {
  name: string;
  university?: string;
  major?: string;
  location?: string;
  graduation_date?: string;
  quality_score?: number;
  best_fit_department?: string;
  top_3_departments?: Department[];
  fit_breakdown?: { experience?: number; projects?: number; learning_potential?: number };
  score_confidence?: { min?: number; max?: number; passes?: number };
  skills?: string[];
  github_url?: string;
  quality_reasoning?: string;
  experience_summary?: string;
}

interface RejectedCandidate {
  name: string;
  location?: string;
  graduation_date?: string;
  rejection_reason?: string;
}

function scoreColor(score: number): string {
  if (score >= 70) return "var(--accent-green)";
  if (score >= 45) return "var(--accent-amber)";
  return "var(--accent-danger)";
}

export default function Overview() {
  const { reportData } = useRun();
  const [candidatesExpanded, setCandidatesExpanded] = useState(false);
  const [rejectedExpanded, setRejectedExpanded] = useState(false);
  const [expandedCandidate, setExpandedCandidate] = useState<string | null>(null);

  if (!reportData) return null;

  const summary = reportData.summary as Summary | undefined;
  const selected = (reportData.selected_candidates as Candidate[]) || [];
  const rejected = (reportData.rejected_candidates as RejectedCandidate[]) || [];

  if (!summary) {
    return <p className="text-sm text-gray-500">No summary data available for this run.</p>;
  }

  const totalProcessed = summary.total_selected + summary.total_rejected;
  const acceptanceRate = totalProcessed > 0
    ? Math.round((summary.total_selected / totalProcessed) * 100)
    : 0;

  const runDate = new Date(summary.pipeline_run);
  const formattedDate = runDate.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

  const topCandidates = [...selected]
    .sort((a, b) => (b.quality_score || 0) - (a.quality_score || 0));

  const previewCount = 5;

  return (
    <div>
      <div className="mb-8">
        <h2 className="text-xl font-semibold tracking-tight">Overview</h2>
        <p className="text-xs text-gray-500 mt-1">{formattedDate}</p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        <MetricCard title="Resumes" value={totalProcessed} subtitle="Processed" />
        <MetricCard title="Accepted" value={summary.total_selected} subtitle={`${acceptanceRate}% rate`} color="var(--accent-green)" />
        <MetricCard title="Rejected" value={summary.total_rejected} subtitle="Failed filter" color="var(--accent-danger)" />
        <MetricCard title="Top Score" value={summary.top_score !== null ? `${summary.top_score}` : "—"}
          subtitle={summary.bottom_selected_score !== null ? `Lowest: ${summary.bottom_selected_score}` : undefined} />
      </div>

      {/* Candidates section */}
      <div className="bg-white rounded-lg border border-gray-200/80 mb-4">
        <div className="p-5">
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              Accepted Candidates ({topCandidates.length})
            </p>
            {topCandidates.length > previewCount && (
              <button
                onClick={() => setCandidatesExpanded(!candidatesExpanded)}
                className="text-[11px] text-[var(--accent-blue)] hover:underline cursor-pointer"
              >
                {candidatesExpanded ? "Show less" : `Show all ${topCandidates.length}`}
              </button>
            )}
          </div>

          {topCandidates.length === 0 ? (
            <p className="text-sm text-gray-500">No scored candidates.</p>
          ) : (
            <div className="space-y-1">
              {(candidatesExpanded ? topCandidates : topCandidates.slice(0, previewCount)).map((c, i) => (
                <div key={i}>
                  <button
                    onClick={() => setExpandedCandidate(expandedCandidate === c.name ? null : c.name)}
                    className="w-full flex items-center justify-between py-2 px-2 -mx-2 rounded-md hover:bg-gray-50 transition-colors cursor-pointer"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-semibold ${
                        i < 3 ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-500"
                      }`}>
                        {i + 1}
                      </span>
                      <span className="text-[13px] font-medium">{c.name}</span>
                      <span className="text-[11px] text-gray-500">{c.university}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-gray-500">{c.best_fit_department}</span>
                      <span className="text-[13px] font-semibold tabular-nums" style={{ color: scoreColor(c.quality_score ?? 0) }}>
                        {c.quality_score}
                      </span>
                      <svg className={`w-3.5 h-3.5 text-gray-500 transition-transform ${expandedCandidate === c.name ? "rotate-180" : ""}`} viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                      </svg>
                    </div>
                  </button>

                  {expandedCandidate === c.name && (
                    <CandidateDetail candidate={c} />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Rejected section */}
      {rejected.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200/80 mb-8">
          <div className="p-5">
            <div className="flex items-center justify-between mb-4">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Rejected ({rejected.length})
              </p>
              <button
                onClick={() => setRejectedExpanded(!rejectedExpanded)}
                className="text-[11px] text-[var(--accent-blue)] hover:underline cursor-pointer"
              >
                {rejectedExpanded ? "Hide details" : "Show details"}
              </button>
            </div>

            {!rejectedExpanded ? (
              <div className="flex flex-wrap gap-2">
                {rejected.map((c, i) => (
                  <span key={i} className="text-[13px] text-gray-600">{c.name}{i < rejected.length - 1 ? "," : ""}</span>
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {rejected.map((c, i) => (
                  <div key={i} className="flex items-start justify-between py-2 border-t border-gray-100 first:border-0 first:pt-0">
                    <div>
                      <p className="text-[13px] font-medium">{c.name}</p>
                      <div className="flex gap-3 mt-0.5">
                        {c.location && <span className="text-[11px] text-gray-500">{c.location}</span>}
                        {c.graduation_date && <span className="text-[11px] text-gray-500">Grad: {c.graduation_date}</span>}
                      </div>
                    </div>
                    <span className="text-[11px] text-orange-600 bg-orange-50 px-2 py-0.5 rounded border border-orange-200/80 shrink-0 ml-3">
                      {c.rejection_reason || "No reason"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Agent capabilities */}
      <div className="bg-white rounded-lg border border-gray-200/80 p-5">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-4">Agent Actions</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[
            { action: "Run the full pipeline", desc: "Parse, filter, score, and sort all resumes end-to-end" },
            { action: "Evaluate resumes for [Workday URL]", desc: "Fetch a job posting and score candidates against it" },
            { action: "List the resumes", desc: "See all available resumes in the Drive folder" },
            { action: "Why was [name] rejected?", desc: "Explain the specific filter rule a candidate failed" },
            { action: "Compare [name] and [name]", desc: "Side-by-side breakdown of two candidates" },
            { action: "Show top candidates for [department]", desc: "Filter scored candidates by department fit" },
          ].map(({ action, desc }) => (
            <div key={action} className="p-3 rounded-md border border-gray-200/80 bg-gray-50/50">
              <p className="text-[13px] font-medium text-gray-800">{action}</p>
              <p className="text-[11px] text-gray-500 mt-0.5">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


function CandidateDetail({ candidate: c }: { candidate: Candidate }) {
  const confidence = c.score_confidence;
  const top3 = c.top_3_departments || [];

  return (
    <div className="ml-8 mr-2 mb-3 mt-1 p-4 bg-gray-50 rounded-md border border-gray-200/80 space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Detail label="Location" value={c.location} />
        <Detail label="Graduation" value={c.graduation_date} />
        <Detail label="Major" value={c.major} />
        <Detail label="Confidence" value={confidence ? `${confidence.min}–${confidence.max}` : undefined} />
      </div>

      {top3.length > 0 && (
        <div>
          <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-2">Department Fits</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {top3.map((dept, i) => (
              <div key={dept.department} className={`p-2.5 rounded-md border ${
                i === 0 ? "border-gray-300 bg-white" : "border-gray-200/80 bg-white"
              }`}>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-[11px] font-medium text-gray-700">{dept.department}</p>
                  <p className="text-[11px] font-semibold tabular-nums">{dept.score}</p>
                </div>
                {dept.experience !== undefined && (
                  <div className="space-y-0.5">
                    <ScoreBar label="Exp" value={dept.experience} max={40} />
                    <ScoreBar label="Proj" value={dept.projects || 0} max={35} />
                    <ScoreBar label="Learn" value={dept.learning_potential || 0} max={25} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {c.skills && c.skills.length > 0 && (
        <div>
          <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1.5">Skills</p>
          <div className="flex flex-wrap gap-1">
            {c.skills.map((skill) => (
              <span key={skill} className="px-1.5 py-0.5 bg-white text-gray-600 rounded text-[10px] border border-gray-200/80">
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {c.github_url && (
        <div>
          <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1">GitHub</p>
          <a href={c.github_url.startsWith("http") ? c.github_url : `https://${c.github_url}`}
            target="_blank" rel="noopener noreferrer"
            className="text-[12px] text-[var(--accent-blue)] hover:underline">
            {c.github_url}
          </a>
        </div>
      )}

      {c.quality_reasoning && (
        <p className="text-[12px] text-gray-500 leading-relaxed">{c.quality_reasoning}</p>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <p className="text-[10px] text-gray-500">{label}</p>
      <p className="text-[13px] font-medium text-gray-800">{value || "—"}</p>
    </div>
  );
}

function ScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.round((value / max) * 100);
  return (
    <div className="flex items-center gap-1 text-[10px]">
      <span className="text-gray-500 w-8">{label}</span>
      <div className="flex-1 bg-gray-200 rounded-full h-1 overflow-hidden">
        <div className="h-full rounded-full" style={{
          width: `${pct}%`,
          backgroundColor: pct >= 70 ? "var(--accent-green)" : pct >= 40 ? "var(--accent-amber)" : "var(--accent-danger)",
        }} />
      </div>
      <span className="text-gray-500 w-6 text-right tabular-nums">{value}/{max}</span>
    </div>
  );
}

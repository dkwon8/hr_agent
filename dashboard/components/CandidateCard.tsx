"use client";

import { useState } from "react";

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
  degree_level?: string;
  quality_score?: number;
  best_fit_department?: string;
  top_3_departments?: Department[];
  fit_breakdown?: {
    experience?: number;
    projects?: number;
    learning_potential?: number;
  };
  score_confidence?: {
    min?: number;
    max?: number;
    median?: number;
    range?: number;
    passes?: number;
  };
  skills?: string[];
  github_url?: string;
  cross_validation_notes?: string[];
  quality_reasoning?: string;
  experience_summary?: string;
}

function scoreColor(score: number): string {
  if (score >= 70) return "var(--accent-green)";
  if (score >= 45) return "var(--accent-amber)";
  return "var(--accent-danger)";
}

export default function CandidateCard({ candidate, rank }: { candidate: Candidate; rank?: number }) {
  const [expanded, setExpanded] = useState(false);

  const c = candidate;
  const confidence = c.score_confidence;
  const top3 = c.top_3_departments || [];

  return (
    <div className={`bg-white rounded-lg border overflow-hidden transition-colors ${
      rank === 1 ? "border-green-200" : "border-gray-200/80"
    }`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-5 py-4 text-left hover:bg-gray-50/50 transition-colors cursor-pointer"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {rank && (
              <span className={`w-6 h-6 rounded flex items-center justify-center text-[11px] font-semibold shrink-0 ${
                rank <= 3 ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-500"
              }`}>
                {rank}
              </span>
            )}
            <div>
              <h3 className="font-medium text-[15px] tracking-tight">{c.name}</h3>
              <p className="text-xs text-gray-400">
                {c.university}{c.major ? ` · ${c.major}` : ""}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-5">
            <div className="text-right">
              <p className="text-lg font-semibold tabular-nums" style={{ color: scoreColor(c.quality_score ?? 0) }}>
                {c.quality_score ?? "—"}<span className="text-xs text-gray-400 font-normal">/100</span>
              </p>
              {confidence && (
                <p className="text-[10px] text-gray-400">{confidence.min}–{confidence.max} range</p>
              )}
            </div>
            <span className="px-2.5 py-1 rounded text-[11px] font-medium bg-gray-100 text-gray-600">
              {c.best_fit_department || "Unscored"}
            </span>
            <svg className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
            </svg>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 border-t border-gray-100 pt-4 space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <Detail label="Location" value={c.location} />
            <Detail label="Graduation" value={c.graduation_date} />
            <Detail label="Degree" value={c.degree_level} capitalize />
            <Detail label="Passes" value={confidence?.passes?.toString()} />
          </div>

          {top3.length > 0 && (
            <div>
              <SectionLabel>Top Department Fits</SectionLabel>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {top3.map((dept, i) => (
                  <div key={dept.department} className={`p-3 rounded-md border ${
                    i === 0 ? "border-gray-300 bg-gray-50" : "border-gray-200/80 bg-gray-50/50"
                  }`}>
                    <div className="flex items-center justify-between mb-2">
                      <p className="font-medium text-xs text-gray-700">{dept.department}</p>
                      <p className="font-semibold text-xs tabular-nums">{dept.score}</p>
                    </div>
                    {dept.experience !== undefined && (
                      <div className="space-y-1">
                        <ScoreBar label="Exp" value={dept.experience} max={40} />
                        <ScoreBar label="Proj" value={dept.projects || 0} max={35} />
                        <ScoreBar label="Learn" value={dept.learning_potential || 0} max={25} />
                      </div>
                    )}
                    {dept.reasoning && (
                      <p className="text-[11px] text-gray-400 mt-2 line-clamp-2">{dept.reasoning}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(c.github_url || (c.cross_validation_notes && c.cross_validation_notes.length > 0)) && (
            <div>
              <SectionLabel>GitHub</SectionLabel>
              <div className="bg-gray-50 rounded-md p-3 text-sm border border-gray-200/80">
                {c.github_url && (
                  <p className="mb-1">
                    <a href={c.github_url.startsWith("http") ? c.github_url : `https://${c.github_url}`}
                      target="_blank" rel="noopener noreferrer"
                      className="text-blue-600 hover:underline text-xs">
                      {c.github_url}
                    </a>
                  </p>
                )}
                {c.cross_validation_notes?.map((note, i) => (
                  <p key={i} className="text-xs text-gray-500">· {note}</p>
                ))}
              </div>
            </div>
          )}

          {c.skills && c.skills.length > 0 && (
            <div>
              <SectionLabel>Skills</SectionLabel>
              <div className="flex flex-wrap gap-1">
                {c.skills.map((skill) => (
                  <span key={skill} className="px-2 py-0.5 bg-gray-50 text-gray-600 rounded text-[11px] border border-gray-200/80">
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}

          {c.quality_reasoning && (
            <div>
              <SectionLabel>Assessment</SectionLabel>
              <p className="text-xs text-gray-500 leading-relaxed">{c.quality_reasoning}</p>
            </div>
          )}

          {c.experience_summary && (
            <div>
              <SectionLabel>Experience</SectionLabel>
              <p className="text-xs text-gray-500 leading-relaxed">{c.experience_summary}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wide mb-2">{children}</p>;
}

function Detail({ label, value, capitalize }: { label: string; value?: string; capitalize?: boolean }) {
  return (
    <div>
      <p className="text-[11px] text-gray-400">{label}</p>
      <p className={`text-sm font-medium ${capitalize ? "capitalize" : ""}`}>{value || "—"}</p>
    </div>
  );
}

function ScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.round((value / max) * 100);
  return (
    <div className="flex items-center gap-1.5 text-[11px]">
      <span className="text-gray-400 w-10">{label}</span>
      <div className="flex-1 bg-gray-200 rounded-full h-1 overflow-hidden">
        <div className="h-full rounded-full" style={{
          width: `${pct}%`,
          backgroundColor: pct >= 70 ? "var(--accent-green)" : pct >= 40 ? "var(--accent-amber)" : "var(--accent-danger)",
        }} />
      </div>
      <span className="text-gray-400 w-7 text-right tabular-nums">{value}/{max}</span>
    </div>
  );
}

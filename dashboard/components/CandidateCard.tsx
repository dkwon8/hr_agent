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

export default function CandidateCard({ candidate }: { candidate: Candidate }) {
  const [expanded, setExpanded] = useState(false);

  const c = candidate;
  const confidence = c.score_confidence;
  const breakdown = c.fit_breakdown;
  const top3 = c.top_3_departments || [];

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-5 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm"
              style={{ backgroundColor: "#3b5998" }}>
              {c.name?.split(" ").map(n => n[0]).join("") || "?"}
            </div>
            <div>
              <h3 className="font-semibold text-lg">{c.name}</h3>
              <p className="text-sm text-gray-500">
                {c.university}{c.major ? ` · ${c.major}` : ""}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="text-right">
              <p className="text-2xl font-bold" style={{ color: "#1a1a2e" }}>
                {c.quality_score ?? "—"}<span className="text-sm text-gray-400">/100</span>
              </p>
              {confidence && (
                <p className="text-xs text-gray-400">
                  Confidence: {confidence.min}–{confidence.max}
                </p>
              )}
            </div>
            <div className="px-3 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
              {c.best_fit_department || "Unscored"}
            </div>
            <span className="text-gray-400 text-lg">{expanded ? "▲" : "▼"}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 border-t border-gray-100 pt-4 space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <p className="text-gray-400 text-xs">Location</p>
              <p className="font-medium">{c.location || "N/A"}</p>
            </div>
            <div>
              <p className="text-gray-400 text-xs">Graduation</p>
              <p className="font-medium">{c.graduation_date || "N/A"}</p>
            </div>
            <div>
              <p className="text-gray-400 text-xs">Degree</p>
              <p className="font-medium capitalize">{c.degree_level || "N/A"}</p>
            </div>
            <div>
              <p className="text-gray-400 text-xs">Scoring Passes</p>
              <p className="font-medium">{confidence?.passes || "N/A"}</p>
            </div>
          </div>

          {top3.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">Top Department Fits</h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {top3.map((dept, i) => (
                  <div key={dept.department} className={`p-3 rounded-lg border ${i === 0 ? "border-blue-200 bg-blue-50" : "border-gray-200 bg-gray-50"}`}>
                    <div className="flex items-center justify-between mb-2">
                      <p className="font-medium text-sm">{i === 0 ? "🏆 " : ""}{dept.department}</p>
                      <p className="font-bold text-sm">{dept.score}/100</p>
                    </div>
                    {dept.experience !== undefined && (
                      <div className="space-y-1">
                        <ScoreBar label="Experience" value={dept.experience} max={40} />
                        <ScoreBar label="Projects" value={dept.projects || 0} max={35} />
                        <ScoreBar label="Learning" value={dept.learning_potential || 0} max={25} />
                      </div>
                    )}
                    {dept.reasoning && (
                      <p className="text-xs text-gray-500 mt-2 line-clamp-3">{dept.reasoning}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(c.github_url || (c.cross_validation_notes && c.cross_validation_notes.length > 0)) && (
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">GitHub Validation</h4>
              <div className="bg-gray-50 rounded-lg p-3 text-sm">
                {c.github_url && (
                  <p className="mb-1">
                    <span className="text-gray-400">Profile: </span>
                    <a href={c.github_url.startsWith("http") ? c.github_url : `https://${c.github_url}`}
                      target="_blank" rel="noopener noreferrer"
                      className="text-blue-600 hover:underline">
                      {c.github_url}
                    </a>
                  </p>
                )}
                {c.cross_validation_notes?.map((note, i) => (
                  <p key={i} className="text-gray-600">• {note}</p>
                ))}
              </div>
            </div>
          )}

          {c.skills && c.skills.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">Skills</h4>
              <div className="flex flex-wrap gap-1.5">
                {c.skills.map((skill) => (
                  <span key={skill} className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs border border-gray-200">
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}

          {c.quality_reasoning && (
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">Overall Assessment</h4>
              <p className="text-sm text-gray-600 bg-gray-50 rounded-lg p-3">{c.quality_reasoning}</p>
            </div>
          )}

          {c.experience_summary && (
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">Experience Summary</h4>
              <p className="text-sm text-gray-600 bg-gray-50 rounded-lg p-3">{c.experience_summary}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.round((value / max) * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-gray-400 w-16">{label}</span>
      <div className="flex-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">
        <div className="h-full rounded-full" style={{
          width: `${pct}%`,
          backgroundColor: pct >= 70 ? "var(--accent-green)" : pct >= 40 ? "var(--accent-amber)" : "var(--redhat-red)",
        }} />
      </div>
      <span className="text-gray-500 w-8 text-right">{value}/{max}</span>
    </div>
  );
}

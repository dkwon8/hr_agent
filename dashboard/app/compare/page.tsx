"use client";

import { useState } from "react";
import { useRun } from "@/components/DashboardShell";

interface Candidate {
  name: string;
  university?: string;
  major?: string;
  location?: string;
  graduation_date?: string;
  quality_score?: number;
  best_fit_department?: string;
  top_3_departments?: { department: string; score: number }[];
  fit_breakdown?: {
    experience?: number;
    projects?: number;
    learning_potential?: number;
  };
  score_confidence?: { min?: number; max?: number };
  skills?: string[];
}

const COLORS = ["#3b5998", "#22c55e", "#f59e0b"];

export default function ComparePage() {
  const { reportData } = useRun();
  const [selected, setSelected] = useState<string[]>([]);

  if (!reportData) return null;

  const candidates = (reportData.selected_candidates as Candidate[]) || [];

  if (candidates.length === 0) {
    return (
      <div>
        <h2 className="text-2xl font-semibold mb-6">Compare Candidates</h2>
        <p className="text-gray-400">No scored candidates to compare.</p>
      </div>
    );
  }

  const toggleCandidate = (name: string) => {
    setSelected((prev) =>
      prev.includes(name)
        ? prev.filter((n) => n !== name)
        : prev.length < 3
          ? [...prev, name]
          : prev
    );
  };

  const selectedCandidates = candidates.filter((c) => selected.includes(c.name));

  const allSkills = new Set<string>();
  selectedCandidates.forEach((c) => c.skills?.forEach((s) => allSkills.add(s)));
  const sharedSkills = [...allSkills].filter((skill) =>
    selectedCandidates.every((c) => c.skills?.includes(skill))
  );

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Compare Candidates</h2>

      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
        <p className="text-sm text-gray-500 mb-3">Select 2–3 candidates to compare</p>
        <div className="flex flex-wrap gap-2">
          {candidates.map((c) => {
            const isSelected = selected.includes(c.name);
            return (
              <button
                key={c.name}
                onClick={() => toggleCandidate(c.name)}
                className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                  isSelected
                    ? "bg-blue-50 border-blue-300 text-blue-700 font-medium"
                    : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}
              >
                {c.name} ({c.quality_score}/100)
              </button>
            );
          })}
        </div>
      </div>

      {selectedCandidates.length < 2 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <p className="text-gray-400">Select at least 2 candidates to see the comparison.</p>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${selectedCandidates.length}, 1fr)` }}>
            {selectedCandidates.map((c, i) => (
              <div key={c.name} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-xs"
                    style={{ backgroundColor: COLORS[i] }}>
                    {c.name.split(" ").map((n) => n[0]).join("")}
                  </div>
                  <div>
                    <h3 className="font-semibold">{c.name}</h3>
                    <p className="text-xs text-gray-500">{c.university}</p>
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Score</span>
                    <span className="font-bold">{c.quality_score}/100</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Confidence</span>
                    <span>{c.score_confidence?.min}–{c.score_confidence?.max}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Best Fit</span>
                    <span className="text-blue-600 text-xs">{c.best_fit_department}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Major</span>
                    <span className="text-xs">{c.major}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Location</span>
                    <span className="text-xs">{c.location}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Graduation</span>
                    <span className="text-xs">{c.graduation_date}</span>
                  </div>
                </div>

                {c.top_3_departments && (
                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <p className="text-xs text-gray-400 mb-1">Top 3 Departments</p>
                    {c.top_3_departments.map((d) => (
                      <div key={d.department} className="flex justify-between text-xs py-0.5">
                        <span className="text-gray-600">{d.department}</span>
                        <span className="font-medium">{d.score}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {sharedSkills.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-medium text-gray-500 mb-3">
                Shared Skills ({sharedSkills.length})
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {sharedSkills.map((skill) => (
                  <span key={skill} className="px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs border border-green-200">
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-medium text-gray-500 mb-3">Unique Skills</h3>
            <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${selectedCandidates.length}, 1fr)` }}>
              {selectedCandidates.map((c, i) => {
                const unique = (c.skills || []).filter(
                  (s) => !selectedCandidates.some((other, j) => j !== i && other.skills?.includes(s))
                );
                return (
                  <div key={c.name}>
                    <p className="text-xs font-medium mb-2" style={{ color: COLORS[i] }}>{c.name}</p>
                    <div className="flex flex-wrap gap-1">
                      {unique.map((skill) => (
                        <span key={skill} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs border border-gray-200">
                          {skill}
                        </span>
                      ))}
                      {unique.length === 0 && <span className="text-xs text-gray-400">No unique skills</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

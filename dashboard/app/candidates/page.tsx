"use client";

import { useRun } from "@/components/DashboardShell";
import CandidateCard from "@/components/CandidateCard";

export default function CandidatesPage() {
  const { reportData } = useRun();

  if (!reportData) return null;

  const candidates = (reportData.selected_candidates as Record<string, unknown>[]) || [];

  if (candidates.length === 0) {
    return (
      <div>
        <h2 className="text-2xl font-semibold mb-6">Candidate Scorecards</h2>
        <p className="text-gray-400">No accepted candidates in this pipeline run.</p>
      </div>
    );
  }

  const sorted = [...candidates].sort(
    (a, b) => ((b.quality_score as number) || 0) - ((a.quality_score as number) || 0)
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold">Candidate Scorecards</h2>
        <p className="text-sm text-gray-400">{sorted.length} accepted candidates</p>
      </div>
      <div className="space-y-3">
        {sorted.map((c, i) => (
          <CandidateCard key={i} candidate={c as never} />
        ))}
      </div>
    </div>
  );
}

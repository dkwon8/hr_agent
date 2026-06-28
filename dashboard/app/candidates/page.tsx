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
        <p className="text-sm text-gray-400">All candidates were filtered out in this run. Check the Rejected tab for details.</p>
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
        <p className="text-sm text-gray-400">{sorted.length} accepted candidates, ranked by score</p>
      </div>
      <div className="space-y-3">
        {sorted.map((c, i) => (
          <CandidateCard key={i} candidate={c as never} rank={i + 1} />
        ))}
      </div>
    </div>
  );
}

"use client";

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

export default function PipelineSummary() {
  const { reportData } = useRun();

  if (!reportData) return null;

  const summary = reportData.summary as Summary | undefined;
  const selected = (reportData.selected_candidates as unknown[]) || [];
  const rejected = (reportData.rejected_candidates as unknown[]) || [];

  if (!summary) {
    return <p className="text-sm text-gray-400">No summary data available for this run.</p>;
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

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-semibold">Pipeline Summary</h2>
        <p className="text-sm text-gray-500 mt-1">Run: {formattedDate}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <MetricCard
          title="Total Resumes"
          value={totalProcessed}
          subtitle="Processed through pipeline"
        />
        <MetricCard
          title="Accepted"
          value={summary.total_selected}
          subtitle={`${acceptanceRate}% acceptance rate`}
          color="var(--accent-green)"
        />
        <MetricCard
          title="Rejected"
          value={summary.total_rejected}
          subtitle="Failed location or graduation filter"
          color="var(--redhat-red)"
        />
        <MetricCard
          title="Top Score"
          value={summary.top_score !== null ? `${summary.top_score}/100` : "N/A"}
          subtitle={summary.bottom_selected_score !== null
            ? `Lowest accepted: ${summary.bottom_selected_score}/100`
            : undefined}
          color="var(--redhat-dark)"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-8">
        <h3 className="text-sm font-medium text-gray-500 mb-3">Acceptance Rate</h3>
        <div className="w-full bg-gray-100 rounded-full h-4 overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${acceptanceRate}%`,
              backgroundColor: "var(--accent-green)",
            }}
          />
        </div>
        <div className="flex justify-between mt-2 text-xs text-gray-400">
          <span>{summary.total_selected} accepted</span>
          <span>{summary.total_rejected} rejected</span>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h3 className="text-sm font-medium text-gray-500 mb-3">Pipeline Steps</h3>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {[
            { step: "Parse Resumes", detail: `${totalProcessed} resumes` },
            { step: "Filter", detail: `${summary.total_selected} passed` },
            { step: "GitHub", detail: "cross-validation" },
            { step: "Score", detail: `top: ${summary.top_score ?? "N/A"}` },
            { step: "Sort & Report", detail: "complete" },
          ].map(({ step, detail }, i) => (
              <div key={step} className="flex items-center gap-2">
                <div className="px-3 py-2 bg-green-50 text-green-700 rounded-lg border border-green-200">
                  <p className="font-medium text-xs">{step}</p>
                  <p className="text-[10px] text-green-600">{detail}</p>
                </div>
                {i < 4 && <span className="text-gray-300">→</span>}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

"use client";

import { useRun } from "@/components/DashboardShell";

interface RejectedCandidate {
  name: string;
  location?: string;
  graduation_date?: string;
  rejection_reason?: string;
}

export default function RejectedPage() {
  const { reportData } = useRun();

  if (!reportData) return null;

  const rejected = (reportData.rejected_candidates as RejectedCandidate[]) || [];

  if (rejected.length === 0) {
    return (
      <div>
        <h2 className="text-2xl font-semibold mb-6">Rejected Candidates</h2>
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <p className="text-gray-400">No candidates were rejected in this pipeline run.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold">Rejected Candidates</h2>
        <p className="text-sm text-gray-400">{rejected.length} rejected</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="text-left px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Location</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Graduation</th>
              <th className="text-left px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Rejection Reason</th>
            </tr>
          </thead>
          <tbody>
            {rejected.map((c, i) => (
              <tr key={i} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                <td className="px-5 py-4 text-sm font-medium">{c.name || "Unknown"}</td>
                <td className="px-5 py-4 text-sm text-gray-600">{c.location || "N/A"}</td>
                <td className="px-5 py-4 text-sm text-gray-600">{c.graduation_date || "N/A"}</td>
                <td className="px-5 py-4 text-sm">
                  <span className="px-2 py-1 bg-orange-50 text-orange-700 rounded text-xs border border-orange-200">
                    {c.rejection_reason || "No reason provided"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

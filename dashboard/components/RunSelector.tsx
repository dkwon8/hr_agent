"use client";

import { useEffect, useState } from "react";

interface Run {
  id: string;
  label: string;
  timestamp: string;
}

interface RunSelectorProps {
  onRunChange: (runId: string) => void;
  selectedRun: string;
}

const API_BASE = "http://localhost:8001";

export default function RunSelector({ onRunChange, selectedRun }: RunSelectorProps) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/runs`)
      .then((res) => res.json())
      .then((data) => {
        setRuns(data.runs || []);
        if (data.runs?.length > 0 && !selectedRun) {
          onRunChange(data.runs[0].id);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="px-4 py-2">
        <p className="text-sm text-gray-400">Loading runs...</p>
      </div>
    );
  }

  return (
    <div className="px-4 py-3 border-b border-gray-200">
      <label className="block text-xs font-medium text-gray-500 mb-1">
        Pipeline Run
      </label>
      <select
        value={selectedRun}
        onChange={(e) => onRunChange(e.target.value)}
        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:border-transparent"
        style={{ focusRingColor: "var(--redhat-red)" } as React.CSSProperties}
      >
        {runs.map((run) => (
          <option key={run.id} value={run.id}>
            {run.label}
          </option>
        ))}
      </select>
    </div>
  );
}

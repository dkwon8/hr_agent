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
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    fetch(`${API_BASE}/api/runs`)
      .then((res) => res.json())
      .then((data) => {
        setRuns(data.runs || []);
        if (data.runs?.length > 0 && !selectedRun) {
          onRunChange(data.runs[0].id);
        }
        setStatus("ok");
      })
      .catch(() => setStatus("error"));
  }, []);

  return (
    <div className="px-5 py-3 border-b border-gray-200 bg-white flex items-center gap-3">
      <label className="text-xs font-medium text-gray-500 shrink-0">
        Pipeline Run
      </label>
      {status === "loading" ? (
        <p className="text-sm text-gray-400">Loading...</p>
      ) : status === "error" ? (
        <p className="text-sm text-red-500">Could not reach API server. Is it running on :8001?</p>
      ) : runs.length === 0 ? (
        <p className="text-sm text-gray-400">No pipeline runs yet. Run the agent to generate results.</p>
      ) : (
        <select
          value={selectedRun}
          onChange={(e) => onRunChange(e.target.value)}
          className="flex-1 max-w-md px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white cursor-pointer hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-300 transition-colors"
        >
          {runs.map((run) => (
            <option key={run.id} value={run.id}>
              {run.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

"use client";

import { createContext, useContext, useState } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import RunSelector from "./RunSelector";

interface RunContextType {
  selectedRun: string;
  reportData: Record<string, unknown> | null;
  loading: boolean;
}

export const RunContext = createContext<RunContextType>({
  selectedRun: "",
  reportData: null,
  loading: false,
});

export function useRun() {
  return useContext(RunContext);
}

const API_BASE = "http://localhost:8001";

export default function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [selectedRun, setSelectedRun] = useState("");
  const [reportData, setReportData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const skipRunRequired = pathname === "/traces";

  const handleRunChange = (runId: string) => {
    setSelectedRun(runId);
    setLoading(true);
    fetch(`${API_BASE}/api/runs/${runId}`)
      .then((res) => res.json())
      .then((data) => {
        setReportData(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  return (
    <RunContext.Provider value={{ selectedRun, reportData, loading }}>
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <RunSelector onRunChange={handleRunChange} selectedRun={selectedRun} />
        <main className="flex-1 p-6 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <p className="text-gray-400">Loading pipeline data...</p>
            </div>
          ) : !reportData && !skipRunRequired ? (
            <div className="flex items-center justify-center h-64">
              <p className="text-gray-400">Select a pipeline run to view results</p>
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </RunContext.Provider>
  );
}

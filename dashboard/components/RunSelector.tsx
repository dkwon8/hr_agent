"use client";

import { useEffect, useState, useRef } from "react";

interface Run {
  id: string;
  label: string;
  timestamp: string;
  title?: string;
  description?: string;
}

interface RunSelectorProps {
  onRunChange: (runId: string) => void;
  selectedRun: string;
}

const API_BASE = "http://localhost:8001";

export default function RunSelector({ onRunChange, selectedRun }: RunSelectorProps) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const selectedItem = runs.find((r) => r.id === selectedRun);

  return (
    <div className="px-8 py-3 border-b border-gray-200/80 bg-white flex items-center gap-3">
      <label className="text-[11px] font-medium text-gray-500 uppercase tracking-wide shrink-0">
        Session
      </label>
      {status === "loading" ? (
        <p className="text-[13px] text-gray-500">Loading...</p>
      ) : status === "error" ? (
        <p className="text-[13px] text-red-500">Could not reach API server on :8001</p>
      ) : runs.length === 0 ? (
        <p className="text-[13px] text-gray-500">No sessions yet.</p>
      ) : (
        <div className="relative" ref={ref}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 text-[13px] border border-gray-200 rounded-md bg-white cursor-pointer hover:border-gray-300 focus:outline-none focus:ring-1 focus:ring-gray-300 transition-colors min-w-[280px]"
          >
            <span className="flex-1 text-left truncate">
              {selectedItem ? (
                selectedItem.title || selectedItem.label
              ) : "Select a session"}
            </span>
            <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform shrink-0 ${dropdownOpen ? "rotate-180" : ""}`} viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
            </svg>
          </button>

          {dropdownOpen && (
            <div className="absolute top-full left-0 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg z-20 max-h-56 overflow-y-auto min-w-[320px]">
              {runs.map((run) => (
                <button
                  key={run.id}
                  onClick={() => { onRunChange(run.id); setDropdownOpen(false); }}
                  className={`w-full text-left px-3 py-2.5 transition-colors cursor-pointer border-b border-gray-100 last:border-0 ${
                    run.id === selectedRun
                      ? "bg-gray-50"
                      : "hover:bg-gray-50"
                  }`}
                >
                  {run.title ? (
                    <>
                      <p className={`text-[13px] ${run.id === selectedRun ? "font-medium text-gray-800" : "text-gray-700"}`}>
                        {run.title}
                      </p>
                      <p className="text-[11px] text-gray-400 mt-0.5">
                        {run.label}{run.description ? ` · ${run.description}` : ""}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className={`text-[13px] ${run.id === selectedRun ? "font-medium text-gray-800" : "text-gray-600"}`}>
                        {run.label}
                      </p>
                      {run.description && (
                        <p className="text-[11px] text-gray-400 mt-0.5">{run.description}</p>
                      )}
                    </>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";

const API_BASE = "http://localhost:8001";

interface Suggestion {
  id: string;
  type: string;
  severity: string;
  title: string;
  description: string;
  action: string;
  confidence: number;
  auto_applicable: boolean;
}

interface Finding {
  pattern: string;
  severity: string;
  description: string;
}

interface Summary {
  status: string;
  traces_analyzed?: number;
  findings_count?: number;
  suggestions_count?: number;
  current_model?: string;
  avg_tool_calls?: number;
  high_severity?: number;
  medium_severity?: number;
  error?: string;
}

interface ImproveData {
  findings: Finding[];
  suggestions: Suggestion[];
  summary: Summary;
}

const SEVERITY_STYLES: Record<string, string> = {
  high: "bg-red-50 text-red-700 border-red-200",
  medium: "bg-orange-50 text-orange-700 border-orange-200",
  low: "bg-yellow-50 text-yellow-700 border-yellow-200",
};

const TYPE_LABELS: Record<string, string> = {
  model_upgrade: "Model",
  prompt_fix: "Prompt",
  config_change: "Config",
  investigate: "Investigate",
};

export default function ImprovePage() {
  const [data, setData] = useState<ImproveData | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  const loadData = () => {
    setStatus("loading");
    fetch(`${API_BASE}/api/improve`)
      .then((res) => res.json())
      .then((d) => {
        setData(d);
        setStatus("ok");
      })
      .catch(() => setStatus("error"));
  };

  useEffect(() => { loadData(); }, []);

  if (status === "loading") {
    return (
      <div>
        <h2 className="text-xl font-semibold tracking-tight mb-6">Improve</h2>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-500 rounded-full animate-spin" />
          <p className="text-[13px] text-gray-500">Analyzing traces...</p>
        </div>
      </div>
    );
  }

  if (status === "error" || !data) {
    return (
      <div>
        <h2 className="text-xl font-semibold tracking-tight mb-6">Improve</h2>
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
          <p className="text-[13px] text-orange-700">Could not analyze traces. Make sure MLflow is running on :5001.</p>
        </div>
      </div>
    );
  }

  const summary = data.summary;
  const healthColor = (summary.high_severity ?? 0) > 0
    ? "text-red-600"
    : (summary.medium_severity ?? 0) > 0
      ? "text-orange-600"
      : "text-green-600";

  const healthLabel = (summary.high_severity ?? 0) > 0
    ? "Needs attention"
    : (summary.medium_severity ?? 0) > 0
      ? "Some issues"
      : "Healthy";

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-xl font-semibold tracking-tight">Improve</h2>
        <button
          onClick={loadData}
          className="text-[12px] text-gray-500 hover:text-gray-700 px-3 py-1.5 border border-gray-200 rounded-md hover:bg-gray-50 transition-colors cursor-pointer"
        >
          Re-analyze
        </button>
      </div>

      {/* Agent health summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        <div className="bg-white rounded-lg border border-gray-200/80 px-5 py-4">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Status</p>
          <p className={`text-lg font-semibold mt-1 ${healthColor}`}>{healthLabel}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200/80 px-5 py-4">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Traces Analyzed</p>
          <p className="text-lg font-semibold mt-1">{summary.traces_analyzed ?? 0}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200/80 px-5 py-4">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Model</p>
          <p className="text-lg font-semibold mt-1">{summary.current_model ?? "—"}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200/80 px-5 py-4">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Avg Tool Calls</p>
          <p className="text-lg font-semibold mt-1">{summary.avg_tool_calls ?? "—"}</p>
        </div>
      </div>

      {/* Suggestions */}
      {data.suggestions.length > 0 ? (
        <div className="mb-8">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-4">
            Suggestions ({data.suggestions.length})
          </p>
          <div className="space-y-3">
            {data.suggestions.map((s) => (
              <div key={s.id} className="bg-white rounded-lg border border-gray-200/80 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[11px] px-2 py-0.5 rounded border font-medium ${SEVERITY_STYLES[s.severity] || "bg-gray-50 text-gray-600 border-gray-200"}`}>
                        {s.severity}
                      </span>
                      <span className="text-[11px] px-2 py-0.5 rounded bg-gray-100 text-gray-600">
                        {TYPE_LABELS[s.type] || s.type}
                      </span>
                      <span className="text-[11px] text-gray-400">
                        {Math.round(s.confidence * 100)}% confidence
                      </span>
                    </div>
                    <p className="text-[14px] font-medium text-gray-800 mt-2">{s.title}</p>
                    <p className="text-[13px] text-gray-500 mt-1">{s.description}</p>
                    <div className="mt-3 p-3 bg-gray-50 rounded-md border border-gray-200/80">
                      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1">Recommended action</p>
                      <p className="text-[13px] text-gray-700">{s.action}</p>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200/80 p-8 mb-8">
          <p className="text-[13px] text-gray-500 text-center">
            No issues detected. The agent is performing within expected parameters.
          </p>
          <p className="text-[11px] text-gray-400 text-center mt-1">
            Run more pipeline sessions to build up trace data for deeper analysis.
          </p>
        </div>
      )}

      {/* Findings detail */}
      {data.findings.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-4">
            Findings ({data.findings.length})
          </p>
          <div className="space-y-2">
            {data.findings.map((f, i) => (
              <div key={i} className="bg-white rounded-lg border border-gray-200/80 px-5 py-3 flex items-start gap-3">
                <span className={`text-[11px] px-2 py-0.5 rounded border font-medium shrink-0 mt-0.5 ${SEVERITY_STYLES[f.severity] || "bg-gray-50 text-gray-600 border-gray-200"}`}>
                  {f.severity}
                </span>
                <div>
                  <p className="text-[13px] font-medium text-gray-700">{f.pattern.replace(/_/g, " ")}</p>
                  <p className="text-[12px] text-gray-500 mt-0.5">{f.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

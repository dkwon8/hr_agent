"use client";

import { useEffect, useState } from "react";

const API_BASE = "http://localhost:8001";

interface TraceListItem {
  trace_id: string;
  timestamp: string;
  status: string;
  execution_time_ms: number;
  request_preview: string;
  response_preview: string;
  mlflow_url?: string;
}

interface Span {
  name: string;
  span_type: string;
  status: string;
  duration_ms: number;
  inputs: string | null;
  outputs: string | null;
}

interface Assessment {
  name: string;
  value: unknown;
  rationale: string | null;
  source: string;
}

interface TraceDetail {
  trace_id: string;
  status: string;
  request_preview: string;
  response_preview: string;
  spans: Span[];
  assessments: Assessment[];
  mlflow_url?: string;
}

const SPAN_TYPE_COLORS: Record<string, string> = {
  AGENT: "#3b5998",
  TOOL: "#22c55e",
  CHAT_MODEL: "#8b5cf6",
  CHAIN: "#6b7280",
  TASK: "#f59e0b",
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function TracesPage() {
  const [traces, setTraces] = useState<TraceListItem[]>([]);
  const [tracesStatus, setTracesStatus] = useState<string>("loading");
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/traces`)
      .then((res) => res.json())
      .then((data) => {
        setTraces(data.traces || []);
        setTracesStatus(data.status || "ok");
      })
      .catch(() => setTracesStatus("error"));
  }, []);

  const loadTrace = (traceId: string) => {
    setLoadingDetail(true);
    fetch(`${API_BASE}/api/traces/${traceId}`)
      .then((res) => res.json())
      .then((data) => {
        setSelectedTrace(data);
        setLoadingDetail(false);
      })
      .catch(() => setLoadingDetail(false));
  };

  if (tracesStatus === "loading") {
    return (
      <div>
        <h2 className="text-2xl font-semibold mb-6">Trace & History</h2>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Loading traces...</p>
        </div>
      </div>
    );
  }

  if (tracesStatus === "unavailable" || tracesStatus === "error") {
    return (
      <div>
        <h2 className="text-2xl font-semibold mb-6">Trace & History</h2>
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
          <p className="text-amber-700 text-sm">
            MLflow server is not running. Start it with <code className="bg-amber-100 px-1 rounded">mlflow server --port 5001</code> to view traces.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Trace & History</h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
              <h3 className="text-sm font-medium text-gray-500">Recent Traces</h3>
            </div>
            <div className="divide-y divide-gray-100 max-h-[600px] overflow-auto">
              {traces.length === 0 ? (
                <p className="p-4 text-sm text-gray-400">No traces found.</p>
              ) : (
                traces.map((t) => (
                  <div
                    key={t.trace_id}
                    className={`p-4 hover:bg-gray-50 transition-colors ${
                      selectedTrace?.trace_id === t.trace_id ? "bg-blue-50" : ""
                    }`}
                  >
                    <button
                      onClick={() => loadTrace(t.trace_id)}
                      className="w-full text-left"
                    >
                      <p className="text-sm font-medium truncate">
                        {t.request_preview || "Agent run"}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-gray-400">
                          {formatDuration(t.execution_time_ms)}
                        </span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          t.status === "OK" ? "bg-green-50 text-green-600" : "bg-red-50 text-red-600"
                        }`}>
                          {t.status}
                        </span>
                      </div>
                    </button>
                    {t.mlflow_url && (
                      <a
                        href={t.mlflow_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-2 text-xs text-blue-600 hover:text-blue-800 hover:underline"
                      >
                        Open in MLflow &#x2197;
                      </a>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="lg:col-span-2">
          {loadingDetail ? (
            <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
              <div className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                <p className="text-sm text-gray-500">Loading trace...</p>
              </div>
            </div>
          ) : !selectedTrace ? (
            <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
              <p className="text-sm text-gray-400">Select a trace from the list to inspect it.</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-gray-500">Prompt</h3>
                  {selectedTrace.mlflow_url && (
                    <a
                      href={selectedTrace.mlflow_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      Open in MLflow &#x2197;
                    </a>
                  )}
                </div>
                <p className="text-sm bg-blue-50 rounded-lg p-3 border border-blue-100">
                  {selectedTrace.request_preview || "N/A"}
                </p>
                <h3 className="text-sm font-medium text-gray-500 mt-4 mb-3">Response</h3>
                <p className="text-sm bg-gray-50 rounded-lg p-3 border border-gray-100 whitespace-pre-wrap max-h-48 overflow-auto">
                  {selectedTrace.response_preview || "N/A"}
                </p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <h3 className="text-sm font-medium text-gray-500 mb-3">
                  Pipeline Steps ({selectedTrace.spans.length} spans)
                </h3>
                <div className="space-y-1.5">
                  {selectedTrace.spans
                    .filter((s) => s.name !== "AgentRunner.run_streamed" && s.name !== "AgentRunner.run")
                    .map((span, i) => {
                      const typeColor = SPAN_TYPE_COLORS[span.span_type] || "#6b7280";
                      return (
                        <SpanRow key={i} span={span} typeColor={typeColor} />
                      );
                    })}
                </div>
              </div>

              {selectedTrace.assessments.length > 0 && (
                <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                  <h3 className="text-sm font-medium text-gray-500 mb-3">Assessments</h3>
                  <div className="space-y-2">
                    {selectedTrace.assessments.map((a, i) => (
                      <div key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">{a.name}</span>
                          <span className="text-sm font-bold">{String(a.value)}</span>
                        </div>
                        {a.rationale && (
                          <p className="text-xs text-gray-500 mt-1">{a.rationale}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SpanRow({ span, typeColor }: { span: Span; typeColor: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
      >
        <span
          className="px-1.5 py-0.5 rounded text-xs text-white font-medium shrink-0"
          style={{ backgroundColor: typeColor }}
        >
          {span.span_type}
        </span>
        <span className="text-sm flex-1 truncate">{span.name}</span>
        <span className="text-xs text-gray-400 shrink-0">{formatDuration(span.duration_ms)}</span>
        <span className="text-gray-400 text-xs">{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded && (
        <div className="ml-8 mr-3 mb-2 text-xs space-y-2">
          {span.inputs && (
            <div>
              <p className="text-gray-400 mb-1">Input:</p>
              <pre className="bg-gray-50 rounded p-2 border border-gray-100 overflow-auto max-h-32 whitespace-pre-wrap">
                {span.inputs}
              </pre>
            </div>
          )}
          {span.outputs && (
            <div>
              <p className="text-gray-400 mb-1">Output:</p>
              <pre className="bg-gray-50 rounded p-2 border border-gray-100 overflow-auto max-h-32 whitespace-pre-wrap">
                {span.outputs}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

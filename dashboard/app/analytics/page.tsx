"use client";

import { useRun } from "@/components/DashboardShell";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell,
} from "recharts";

interface Department {
  department: string;
  score: number;
  experience?: number;
  projects?: number;
  learning_potential?: number;
}

interface Candidate {
  name: string;
  quality_score?: number;
  best_fit_department?: string;
  department_scores?: Record<string, { score: number }>;
  fit_breakdown?: {
    experience?: number;
    projects?: number;
    learning_potential?: number;
  };
}

export default function AnalyticsPage() {
  const { reportData } = useRun();

  if (!reportData) return null;

  const candidates = (reportData.selected_candidates as Candidate[]) || [];

  if (candidates.length === 0) {
    return (
      <div>
        <h2 className="text-2xl font-semibold mb-6">Department Analytics</h2>
        <p className="text-gray-400">No scored candidates in this pipeline run.</p>
      </div>
    );
  }

  const bestFitCounts: Record<string, number> = {};
  candidates.forEach((c) => {
    const dept = c.best_fit_department || "Unknown";
    bestFitCounts[dept] = (bestFitCounts[dept] || 0) + 1;
  });
  const bestFitData = Object.entries(bestFitCounts)
    .map(([dept, count]) => ({ department: dept, candidates: count }))
    .sort((a, b) => b.candidates - a.candidates);

  const deptScoreAverages: Record<string, { total: number; count: number }> = {};
  candidates.forEach((c) => {
    if (c.department_scores) {
      Object.entries(c.department_scores).forEach(([dept, data]) => {
        if (!deptScoreAverages[dept]) deptScoreAverages[dept] = { total: 0, count: 0 };
        deptScoreAverages[dept].total += data.score;
        deptScoreAverages[dept].count += 1;
      });
    }
  });
  const avgScoreData = Object.entries(deptScoreAverages)
    .map(([dept, { total, count }]) => ({
      department: dept.length > 20 ? dept.slice(0, 20) + "…" : dept,
      avgScore: Math.round(total / count),
    }))
    .sort((a, b) => b.avgScore - a.avgScore);

  const scoreDistribution: Record<string, number> = {};
  candidates.forEach((c) => {
    const score = c.quality_score || 0;
    const bucket = `${Math.floor(score / 10) * 10}-${Math.floor(score / 10) * 10 + 9}`;
    scoreDistribution[bucket] = (scoreDistribution[bucket] || 0) + 1;
  });
  const histogramData = Object.entries(scoreDistribution)
    .map(([range, count]) => ({ range, count }))
    .sort((a, b) => a.range.localeCompare(b.range));

  const breakdownData = candidates
    .filter((c) => c.fit_breakdown)
    .map((c) => ({
      name: c.name?.split(" ")[0] || "?",
      experience: c.fit_breakdown?.experience || 0,
      projects: c.fit_breakdown?.projects || 0,
      learning_potential: c.fit_breakdown?.learning_potential || 0,
    }));

  const COLORS = ["#3b5998", "#5b7dc7", "#7c9ee6", "#9dbef5", "#bdd6ff"];

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-6">Department Analytics</h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="text-sm font-medium text-gray-500 mb-4">Best-Fit Department Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={bestFitData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="department" width={150} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="candidates" radius={[0, 4, 4, 0]}>
                {bestFitData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {avgScoreData.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-medium text-gray-500 mb-4">Average Score by Department</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={avgScoreData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis type="number" domain={[0, 100]} />
                <YAxis type="category" dataKey="department" width={150} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="avgScore" fill="#3b5998" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="text-sm font-medium text-gray-500 mb-4">Score Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={histogramData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="range" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#22c55e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {breakdownData.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-medium text-gray-500 mb-4">Score Breakdown by Candidate</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={breakdownData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Legend />
                <Bar dataKey="experience" fill="#3b5998" name="Experience (0-40)" stackId="a" />
                <Bar dataKey="projects" fill="#22c55e" name="Projects (0-35)" stackId="a" />
                <Bar dataKey="learning_potential" fill="#f59e0b" name="Learning Potential (0-25)" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: string;
}

export default function MetricCard({ title, value, subtitle, color }: MetricCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <p className="text-sm font-medium text-gray-500">{title}</p>
      <p className="text-3xl font-bold mt-1" style={{ color: color || "var(--foreground)" }}>
        {value}
      </p>
      {subtitle && (
        <p className="text-sm text-gray-400 mt-1">{subtitle}</p>
      )}
    </div>
  );
}

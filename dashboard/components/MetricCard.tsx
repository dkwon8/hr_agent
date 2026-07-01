"use client";

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: string;
}

export default function MetricCard({ title, value, subtitle, color }: MetricCardProps) {
  return (
    <div className="bg-white rounded-lg border border-gray-200/80 px-5 py-4">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
      <p className="text-2xl font-semibold mt-1 tracking-tight" style={{ color: color || "var(--foreground)" }}>
        {value}
      </p>
      {subtitle && (
        <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
      )}
    </div>
  );
}

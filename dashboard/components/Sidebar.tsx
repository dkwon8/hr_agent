"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Pipeline Summary", icon: "📊" },
  { href: "/candidates", label: "Candidate Scorecards", icon: "👤" },
  { href: "/rejected", label: "Rejected Candidates", icon: "❌" },
  { href: "/analytics", label: "Department Analytics", icon: "📈" },
  { href: "/compare", label: "Compare Candidates", icon: "⚖️" },
  { href: "/traces", label: "Trace & History", icon: "🔍" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 min-h-screen flex flex-col"
      style={{ backgroundColor: "var(--sidebar-bg)" }}>
      <div className="p-5 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded flex items-center justify-center text-white font-bold text-sm"
            style={{ backgroundColor: "var(--redhat-red)" }}>
            RH
          </div>
          <div>
            <h1 className="text-white font-semibold text-sm">Red Hat</h1>
            <p className="text-xs" style={{ color: "var(--sidebar-text)" }}>
              HR Recruitment Dashboard
            </p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-white/15 text-white font-medium"
                  : "text-gray-400 hover:bg-white/5 hover:text-white"
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-white/10">
        <p className="text-xs text-gray-500">
          Powered by AI Recruitment Agent
        </p>
      </div>
    </aside>
  );
}

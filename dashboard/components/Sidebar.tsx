"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/compare", label: "Compare" },
  { href: "/traces", label: "Traces" },
  { href: "/improve", label: "Improve" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 min-h-screen flex flex-col"
      style={{ backgroundColor: "var(--sidebar-bg)" }}>
      <div className="px-5 py-6 border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded flex items-center justify-center text-white font-semibold text-xs"
            style={{ backgroundColor: "var(--redhat-red)" }}>
            RH
          </div>
          <div>
            <h1 className="text-white font-medium text-[13px] tracking-tight">Red Hat</h1>
            <p className="text-[11px] text-gray-500">Recruitment</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block px-3 py-2 rounded-md text-[13px] transition-colors ${
                isActive
                  ? "bg-white/10 text-white font-medium"
                  : "text-gray-400 hover:bg-white/[0.04] hover:text-gray-300"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-5 py-4 border-t border-white/[0.06]">
        <p className="text-[11px] text-gray-600">AI Recruitment Agent</p>
      </div>
    </aside>
  );
}

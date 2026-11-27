"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  CheckSquare,
  Download,
  LayoutDashboard,
  Mail,
  Mic,
  Settings,
  UserCheck,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Agent Workspace", icon: Bot },
  { href: "/dashboard", label: "Research Dashboard", icon: LayoutDashboard },
  { href: "/podcasts", label: "Podcast Research", icon: Mic },
  { href: "/hosts", label: "Host Research", icon: UserCheck },
  { href: "/contacts", label: "Contact Research", icon: Mail },
  { href: "/review", label: "Manual Review", icon: CheckSquare },
  { href: "/exports", label: "Export Center", icon: Download },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 shrink-0 border-r border-slate-800 bg-slate-950/90 flex flex-col">
      <div className="p-5 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-lg bg-cyan-500/15 border border-cyan-400/40 flex items-center justify-center text-cyan-300 font-bold">
            JV
          </div>
          <div>
            <div className="text-sm font-semibold text-white tracking-tight">Jarvis AI</div>
            <div className="text-[11px] text-slate-400">Autonomous Research Agent</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                  : "text-slate-300 hover:bg-slate-800/70 hover:text-white border border-transparent"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-slate-800 text-xs text-slate-400 space-y-1">
        <div className="font-medium text-slate-300">Scope: Podcast Host Research</div>
        <div>LinkedIn • YouTube • Google • Apollo</div>
      </div>
    </aside>
  );
}


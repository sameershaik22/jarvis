"use client";

export function StatusBadge({ status }: { status?: string | null }) {
  const val = status || "Pending";
  const styles: Record<string, string> = {
    Verified: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    Qualified: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    completed: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    running: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
    "Partially Verified": "bg-amber-500/15 text-amber-300 border-amber-500/30",
    "Possible Match": "bg-amber-500/15 text-amber-300 border-amber-500/30",
    paused: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    "Manual Review": "bg-orange-500/15 text-orange-300 border-orange-500/30",
    "Manual Review Required": "bg-orange-500/15 text-orange-300 border-orange-500/30",
    Rejected: "bg-rose-500/15 text-rose-300 border-rose-500/30",
    failed: "bg-rose-500/15 text-rose-300 border-rose-500/30",
    stopped: "bg-rose-500/15 text-rose-300 border-rose-500/30",
    Unverified: "bg-slate-700/60 text-slate-300 border-slate-600",
    Pending: "bg-slate-700/60 text-slate-300 border-slate-600",
  };
  const cls = styles[val] || "bg-slate-700/60 text-slate-200 border-slate-600";
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {val}
    </span>
  );
}


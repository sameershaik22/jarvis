"use client";

import { useEffect, useState } from "react";
import { Database, RefreshCw } from "lucide-react";
import { apiFetch, LeadRecord } from "@/lib/api";
import { ExportControls } from "@/components/ExportControls";
import { StatusBadge } from "@/components/StatusBadge";

interface OverviewData {
  statistics: {
    total_research_tasks: number;
    linkedin_videos_discovered: number;
    qualified_podcasts: number;
    rejected_videos: number;
    hosts_identified: number;
    companies_identified: number;
    emails_discovered: number;
    verified_contacts: number;
    pending_manual_reviews: number;
  };
  recent_leads: LeadRecord[];
  database_status: {
    configured: boolean;
    provider: string;
    host: string;
    connected: boolean;
  };
}

export default function ResearchDashboardPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await apiFetch<OverviewData>("/api/v1/dashboard/overview");
      setData(res);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const stats = data?.statistics;
  const cards = stats
    ? [
        { label: "Total Research Tasks", val: stats.total_research_tasks },
        { label: "LinkedIn Videos Discovered", val: stats.linkedin_videos_discovered },
        { label: "Qualified Podcasts", val: stats.qualified_podcasts },
        { label: "Rejected Videos", val: stats.rejected_videos },
        { label: "Hosts Identified", val: stats.hosts_identified },
        { label: "Companies Identified", val: stats.companies_identified },
        { label: "Emails Discovered", val: stats.emails_discovered },
        { label: "Verified Contacts", val: stats.verified_contacts },
        { label: "Pending Manual Reviews", val: stats.pending_manual_reviews },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Research Dashboard</h1>
          <p className="text-sm text-slate-400 mt-1">
            Real-time metrics computed directly from PostgreSQL research tables.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={load}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sm text-slate-200 cursor-pointer"
          >
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
          <ExportControls label="Download" />
        </div>
      </div>

      {data?.database_status && (
        <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 w-fit">
          <Database className="w-4 h-4 text-cyan-400" />
          <span>
            Database: <strong>{data.database_status.provider}</strong> ({data.database_status.host}) —{" "}
            {data.database_status.connected ? "Connected" : "Disconnected"}
          </span>
        </div>
      )}

      {loading && !data ? (
        <div className="text-sm text-slate-400">Loading dashboard metrics...</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {cards.map((c) => (
            <div key={c.label} className="rounded-xl bg-slate-900/80 border border-slate-800 p-4">
              <div className="text-xs uppercase tracking-wider text-slate-400">{c.label}</div>
              <div className="text-3xl font-bold text-white mt-2">{c.val}</div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-xl bg-slate-900/80 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="font-semibold text-white text-sm">Recent Discovered Podcast Hosts</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-950/60 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Podcast</th>
                <th className="px-4 py-3">Host</th>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Quality</th>
                <th className="px-4 py-3">Verification</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {(!data?.recent_leads || data.recent_leads.length === 0) && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                    No research leads recorded yet. Start a research task in Agent Workspace.
                  </td>
                </tr>
              )}
              {data?.recent_leads.map((r) => (
                <tr key={r.lead_id} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium text-white">{r.podcast_name}</td>
                  <td className="px-4 py-3 text-slate-200">{r.host_full_name || "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{r.host_company || "—"}</td>
                  <td className="px-4 py-3 text-cyan-300">{r.business_email || "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.qualification_status} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.identity_verification_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


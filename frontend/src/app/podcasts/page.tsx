"use client";

import { useEffect, useState } from "react";
import { apiFetch, LeadRecord } from "@/lib/api";
import { ExportControls } from "@/components/ExportControls";
import { StatusBadge } from "@/components/StatusBadge";

export default function PodcastResearchPage() {
  const [rows, setRows] = useState<LeadRecord[]>([]);
  const [search, setSearch] = useState("");
  const [qualFilter, setQualFilter] = useState("");
  const [sortAsc, setSortAsc] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  async function load() {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (qualFilter) params.set("qualification_status", qualFilter);
    const data = await apiFetch<LeadRecord[]>(`/api/v1/research/results?${params.toString()}`);
    setRows(data);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qualFilter]);

  const sorted = [...rows].sort((a, b) => {
    const sa = a.video_quality_score ?? 0;
    const sb = b.video_quality_score ?? 0;
    return sortAsc ? sa - sb : sb - sa;
  });

  function toggleSelect(id: number) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  const exportFilters = {
    qualification_status: qualFilter || null,
    selected_ids: selectedIds.length > 0 ? selectedIds : null,
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Podcast Research</h1>
          <p className="text-sm text-slate-400 mt-1">
            Discovered LinkedIn podcast videos, quality scores, original podcast links, and hosts.
          </p>
        </div>
        <ExportControls
          filters={exportFilters}
          label={selectedIds.length > 0 ? `Export Selected (${selectedIds.length})` : "Export"}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          placeholder="Search podcast, episode, host..."
          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white w-72"
        />
        <select
          value={qualFilter}
          onChange={(e) => setQualFilter(e.target.value)}
          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
        >
          <option value="">All Qualification Statuses</option>
          <option value="Qualified">Qualified</option>
          <option value="Manual Review">Manual Review</option>
          <option value="Rejected">Rejected</option>
        </select>
        <button
          type="button"
          onClick={() => setSortAsc((s) => !s)}
          className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-slate-200 cursor-pointer"
        >
          Sort Score ({sortAsc ? "Low → High" : "High → Low"})
        </button>
        <button
          type="button"
          onClick={load}
          className="px-3 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white cursor-pointer"
        >
          Apply Search
        </button>
      </div>

      <div className="rounded-xl bg-slate-900/80 border border-slate-800 overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-950/60 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-3 py-3">Sel</th>
              <th className="px-4 py-3">Podcast</th>
              <th className="px-4 py-3">Episode</th>
              <th className="px-4 py-3">LinkedIn Post</th>
              <th className="px-4 py-3">YouTube Channel</th>
              <th className="px-4 py-3">Host</th>
              <th className="px-4 py-3">Quality Score</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Research Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {sorted.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-6 text-center text-slate-500">
                  No podcast records match the current filters.
                </td>
              </tr>
            )}
            {sorted.map((r) => (
              <tr key={r.lead_id} className="hover:bg-slate-800/40">
                <td className="px-3 py-3">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(r.lead_id)}
                    onChange={() => toggleSelect(r.lead_id)}
                  />
                </td>
                <td className="px-4 py-3 font-medium text-white">{r.podcast_name}</td>
                <td className="px-4 py-3 text-slate-300 max-w-xs truncate">{r.episode_title || "—"}</td>
                <td className="px-4 py-3">
                  {r.linkedin_post_url ? (
                    <a href={r.linkedin_post_url} target="_blank" rel="noreferrer" className="text-cyan-400 underline">
                      View Post
                    </a>
                  ) : "—"}
                </td>
                <td className="px-4 py-3">
                  {r.youtube_channel_url ? (
                    <a href={r.youtube_channel_url} target="_blank" rel="noreferrer" className="text-cyan-400 underline">
                      {r.youtube_channel_name || "YouTube Channel"}
                    </a>
                  ) : "—"}
                </td>
                <td className="px-4 py-3 text-slate-200">{r.host_full_name || "—"}</td>
                <td className="px-4 py-3 font-semibold text-white">{r.video_quality_score ?? "—"}</td>
                <td className="px-4 py-3"><StatusBadge status={r.qualification_status} /></td>
                <td className="px-4 py-3 text-slate-400">
                  {r.research_date ? new Date(r.research_date).toLocaleDateString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


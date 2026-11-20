"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

interface HostItem {
  id: number;
  full_name: string;
  linkedin_url: string | null;
  designation: string | null;
  location: string | null;
  identity_status: string;
  confidence_score: number;
  manual_review_required: boolean;
  notes: string | null;
  companies: {
    id: number;
    company_name: string;
    linkedin_url: string | null;
    website: string | null;
    relationship_status: string;
  }[];
  podcasts: { id: number; podcast_name: string; youtube_channel_url: string | null }[];
}

interface EvidenceItem {
  id: number;
  source_url: string;
  source_type: string;
  extracted_information: string;
  collected_at: string;
}

export default function HostResearchPage() {
  const [hosts, setHosts] = useState<HostItem[]>([]);
  const [evidenceMap, setEvidenceMap] = useState<Record<number, EvidenceItem[]>>({});

  useEffect(() => {
    apiFetch<HostItem[]>("/api/v1/research/hosts").then(setHosts);
  }, []);

  async function toggleEvidence(hostId: number) {
    if (evidenceMap[hostId]) {
      const next = { ...evidenceMap };
      delete next[hostId];
      setEvidenceMap(next);
      return;
    }
    const items = await apiFetch<EvidenceItem[]>(
      `/api/v1/research/evidence?entity_type=person&entity_id=${hostId}`
    );
    setEvidenceMap((prev) => ({ ...prev, [hostId]: items }));
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Host Research</h1>
        <p className="text-sm text-slate-400 mt-1">
          Identified podcast hosts, LinkedIn profiles, verified companies, and supporting research evidence.
        </p>
      </div>

      <div className="rounded-xl bg-slate-900/80 border border-slate-800 overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-950/60 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-4 py-3">Host Name</th>
              <th className="px-4 py-3">LinkedIn Profile</th>
              <th className="px-4 py-3">Company</th>
              <th className="px-4 py-3">Designation</th>
              <th className="px-4 py-3">Podcast</th>
              <th className="px-4 py-3">Identity Verification</th>
              <th className="px-4 py-3">Evidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {hosts.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-slate-500">
                  No podcast hosts identified yet.
                </td>
              </tr>
            )}
            {hosts.map((h) => (
              <>
                <tr key={h.id} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium text-white">{h.full_name}</td>
                  <td className="px-4 py-3">
                    {h.linkedin_url ? (
                      <a href={h.linkedin_url} target="_blank" rel="noreferrer" className="text-cyan-400 underline">
                        LinkedIn Profile
                      </a>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-200">
                    {h.companies[0]?.company_name || "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-300">{h.designation || "—"}</td>
                  <td className="px-4 py-3 text-slate-300">
                    {h.podcasts.map((p) => p.podcast_name).join(", ") || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={h.identity_status} />
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => toggleEvidence(h.id)}
                      className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-cyan-300 cursor-pointer"
                    >
                      {evidenceMap[h.id] ? "Hide Evidence" : "View Evidence"}
                    </button>
                  </td>
                </tr>
                {evidenceMap[h.id] && (
                  <tr key={`ev-${h.id}`} className="bg-slate-950/70">
                    <td colSpan={7} className="px-6 py-3 space-y-1.5 text-xs text-slate-300">
                      <div className="font-semibold text-cyan-300">Supporting Research Evidence:</div>
                      {evidenceMap[h.id].length === 0 && <div>No stored evidence rows.</div>}
                      {evidenceMap[h.id].map((ev) => (
                        <div key={ev.id} className="border-l-2 border-cyan-500/40 pl-3">
                          <span className="font-medium text-white">[{ev.source_type}]</span>{" "}
                          <a href={ev.source_url} target="_blank" rel="noreferrer" className="text-cyan-400 underline">
                            {ev.source_url}
                          </a>
                          <div className="text-slate-400">{ev.extracted_information}</div>
                        </div>
                      ))}
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


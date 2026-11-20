"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

interface ContactItem {
  id: number;
  host_name: string | null;
  podcast_name: string | null;
  email: string | null;
  email_category: string;
  phone: string | null;
  official_website: string | null;
  verification_status: string;
  confidence_score: number;
  sources: { id: number; source_type: string; source_url: string; discovery_method: string }[];
}

export default function ContactResearchPage() {
  const [contacts, setContacts] = useState<ContactItem[]>([]);

  useEffect(() => {
    apiFetch<ContactItem[]>("/api/v1/research/contacts").then(setContacts);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Contact Research</h1>
        <p className="text-sm text-slate-400 mt-1">
          Host business emails categorized by direct/podcast/company/channel inquiry with full source traceability.
        </p>
      </div>

      <div className="rounded-xl bg-slate-900/80 border border-slate-800 overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="bg-slate-950/60 text-xs uppercase text-slate-400">
            <tr>
              <th className="px-4 py-3">Host Name</th>
              <th className="px-4 py-3">Podcast</th>
              <th className="px-4 py-3">Business Email</th>
              <th className="px-4 py-3">Email Category</th>
              <th className="px-4 py-3">Phone</th>
              <th className="px-4 py-3">Contact Source</th>
              <th className="px-4 py-3">Verification</th>
              <th className="px-4 py-3">Confidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {contacts.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-slate-500">
                  No contact records discovered yet.
                </td>
              </tr>
            )}
            {contacts.map((c) => (
              <tr key={c.id} className="hover:bg-slate-800/40">
                <td className="px-4 py-3 font-medium text-white">{c.host_name || "—"}</td>
                <td className="px-4 py-3 text-slate-300">{c.podcast_name || "—"}</td>
                <td className="px-4 py-3 text-cyan-300">{c.email || "Not found"}</td>
                <td className="px-4 py-3 text-slate-300">{c.email_category}</td>
                <td className="px-4 py-3 text-slate-300">{c.phone || "—"}</td>
                <td className="px-4 py-3">
                  {c.sources[0] ? (
                    <a
                      href={c.sources[0].source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-cyan-400 underline"
                    >
                      {c.sources[0].source_type}
                    </a>
                  ) : "—"}
                </td>
                <td className="px-4 py-3"><StatusBadge status={c.verification_status} /></td>
                <td className="px-4 py-3 font-semibold text-white">{c.confidence_score}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


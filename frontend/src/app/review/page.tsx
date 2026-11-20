"use client";

import { useEffect, useState } from "react";
import { apiFetch, LeadRecord } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function ManualReviewPage() {
  const [items, setItems] = useState<LeadRecord[]>([]);
  const [edits, setEdits] = useState<Record<number, { host?: string; company?: string; email?: string; youtube?: string; notes?: string }>>({});
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    const data = await apiFetch<LeadRecord[]>("/api/v1/verification/manual-review");
    setItems(data);
  }

  useEffect(() => {
    load();
  }, []);

  async function submitAction(r: LeadRecord, action: "approve" | "reject" | "request_recheck") {
    const e = edits[r.lead_id] || {};
    await apiFetch("/api/v1/verification/manual-review", {
      method: "POST",
      body: JSON.stringify({
        podcast_id: r.podcast_id,
        host_id: r.host_id,
        contact_id: r.contact_id,
        action,
        corrected_host_name: e.host || null,
        corrected_company_name: e.company || null,
        corrected_email: e.email || null,
        corrected_youtube_url: e.youtube || null,
        notes: e.notes || null,
      }),
    });
    setMsg(`Applied '${action}' to lead #${r.lead_id}.`);
    await load();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Manual Review Queue</h1>
        <p className="text-sm text-slate-400 mt-1">
          Verify uncertain host identities, correct company or contact details, or request additional verification.
        </p>
      </div>

      {msg && (
        <div className="p-3 rounded-lg bg-emerald-950/60 border border-emerald-700 text-emerald-200 text-sm">
          {msg}
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-8 text-center text-slate-400 text-sm">
          No records currently require manual review.
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((r) => {
            const e = edits[r.lead_id] || {};
            return (
              <div key={r.lead_id} className="rounded-xl bg-slate-900/80 border border-slate-800 p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold text-white">{r.podcast_name}</div>
                    <div className="text-xs text-slate-400 mt-0.5">{r.research_notes || "Requires verification"}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={r.qualification_status} />
                    <StatusBadge status={r.identity_verification_status} />
                    <StatusBadge status={r.contact_verification_status} />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
                  <input
                    placeholder={r.host_full_name || "Confirm Host Name"}
                    value={e.host ?? ""}
                    onChange={(ev) => setEdits({ ...edits, [r.lead_id]: { ...e, host: ev.target.value } })}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
                  />
                  <input
                    placeholder={r.host_company || "Confirm Company Name"}
                    value={e.company ?? ""}
                    onChange={(ev) => setEdits({ ...edits, [r.lead_id]: { ...e, company: ev.target.value } })}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
                  />
                  <input
                    placeholder={r.business_email || "Confirm Business Email"}
                    value={e.email ?? ""}
                    onChange={(ev) => setEdits({ ...edits, [r.lead_id]: { ...e, email: ev.target.value } })}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
                  />
                  <input
                    placeholder={r.youtube_channel_url || "Confirm YouTube Channel URL"}
                    value={e.youtube ?? ""}
                    onChange={(ev) => setEdits({ ...edits, [r.lead_id]: { ...e, youtube: ev.target.value } })}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex gap-3 text-xs">
                    {r.linkedin_post_url && (
                      <a href={r.linkedin_post_url} target="_blank" rel="noreferrer" className="text-cyan-400 underline">
                        LinkedIn Post
                      </a>
                    )}
                    {r.host_linkedin_url && (
                      <a href={r.host_linkedin_url} target="_blank" rel="noreferrer" className="text-cyan-400 underline">
                        Host LinkedIn
                      </a>
                    )}
                    {r.youtube_channel_url && (
                      <a href={r.youtube_channel_url} target="_blank" rel="noreferrer" className="text-cyan-400 underline">
                        YouTube Channel
                      </a>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => submitAction(r, "approve")}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium cursor-pointer"
                    >
                      Approve & Verify
                    </button>
                    <button
                      type="button"
                      onClick={() => submitAction(r, "request_recheck")}
                      className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium cursor-pointer"
                    >
                      Request Additional Research
                    </button>
                    <button
                      type="button"
                      onClick={() => submitAction(r, "reject")}
                      className="px-3 py-1.5 rounded-lg bg-rose-700 hover:bg-rose-600 text-white text-xs font-medium cursor-pointer"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


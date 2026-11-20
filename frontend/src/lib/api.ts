export const API_BASE =
  process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "") || "";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || `Request failed with ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface LeadRecord {
  lead_id: number;
  linkedin_post_id: number | null;
  podcast_id: number | null;
  host_id: number | null;
  company_id: number | null;
  contact_id: number | null;
  research_task_id: number | null;
  podcast_name: string;
  episode_title: string | null;
  linkedin_post_url: string | null;
  video_posting_date: string | null;
  youtube_channel_name: string | null;
  youtube_channel_url: string | null;
  original_podcast_url: string | null;
  host_full_name: string | null;
  host_designation: string | null;
  host_linkedin_url: string | null;
  host_company: string | null;
  company_linkedin_url: string | null;
  company_website: string | null;
  company_location: string | null;
  business_email: string | null;
  email_category: string | null;
  phone: string | null;
  contact_source: string | null;
  contact_source_url: string | null;
  video_quality_score: number | null;
  video_quality: string | null;
  audio_quality: string | null;
  lighting: string | null;
  podcast_setup: string | null;
  content_relevance: string | null;
  qualification_status: string | null;
  identity_verification_status: string | null;
  contact_verification_status: string | null;
  confidence_score: number;
  manual_review_required: boolean;
  research_date: string | null;
  research_notes: string | null;
}

export interface ExportFiltersPayload {
  preset?: string;
  qualification_status?: string | null;
  identity_verification_status?: string | null;
  contact_verification_status?: string | null;
  has_email?: boolean | null;
  company?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  min_quality_score?: number | null;
  research_task_id?: number | null;
  selected_ids?: number[] | null;
}

export async function downloadExportFile(
  format: "excel" | "csv",
  filters: ExportFiltersPayload = {}
): Promise<{ filename: string; recordCount: number }> {
  const endpoint = format === "excel" ? "/api/v1/export/excel" : "/api/v1/export/csv";
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filters),
  });
  if (!res.ok) {
    throw new Error(`Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const ext = format === "excel" ? "xlsx" : "csv";
  const filename = match ? match[1] : `YoursBuddy_Podcast_Host_Research.${ext}`;
  const recordCount = Number(res.headers.get("X-Export-Record-Count") || "0");

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
  return { filename, recordCount };
}


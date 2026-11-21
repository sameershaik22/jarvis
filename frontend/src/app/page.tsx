"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Bot,
  Database,
  ExternalLink,
  FileSpreadsheet,
  Globe,
  Info,
  Laptop,
  Mail,
  Mic,
  Pause,
  Play,
  RotateCcw,
  Send,
  Square,
  Terminal,
  UserCheck,
  X,
} from "lucide-react";
import { API_BASE, apiFetch, getApiBase } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { ExportControls } from "@/components/ExportControls";

interface LeadItem {
  lead_id: number;
  podcast_name: string;
  episode_title?: string | null;
  host_full_name?: string | null;
  host_company?: string | null;
  business_email?: string | null;
  qualification_status: string;
  identity_verification_status: string;
  video_quality_score?: number | null;
  youtube_channel_url?: string | null;
  original_podcast_url?: string | null;
  research_date?: string | null;
}

interface AgentStatus {
  agent_state: string;
  browser_active: boolean;
  browser_status?: string;
  bridge_connected?: boolean;
  device_name?: string | null;
  agency_id?: string;
  linkedin_authenticated?: boolean;
  youtube_authenticated?: boolean;
  current_url: string | null;
  current_website: string | null;
  latest_screenshot_url: string | null;
  active_task: {
    id: number;
    user_instruction: string;
    search_keyword: string;
    task_status: string;
    current_stage: string;
    current_url: string | null;
    progress: number;
  } | null;
  recent_logs: {
    id: number;
    level: string;
    stage: string;
    action: string;
    url: string | null;
    message: string;
    created_at: string;
  }[];
  messages: {
    id: number;
    role: string;
    content: string;
    metadata_json?: { download_url?: string } | null;
    created_at: string;
  }[];
  recent_leads?: LeadItem[];
  stats?: {
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
}

function renderBrowserBadge(status?: string, isActive?: boolean, bridgeConnected?: boolean, deviceName?: string | null) {
  if (bridgeConnected) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/90 text-emerald-400 border border-emerald-700/60 shadow-sm">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Local Chrome Connected ({deviceName || "Desktop"})
      </span>
    );
  }
  const norm = (status || "").toLowerCase().trim();
  if (norm === "research in progress") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/90 text-emerald-400 border border-emerald-700/60 shadow-sm">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Research in progress
      </span>
    );
  }
  if (norm === "waiting for manual login") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950/90 text-amber-400 border border-amber-700/60 shadow-sm">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        Chrome Tab Ready (Sign In / Active)
      </span>
    );
  }
  if (norm === "linkedin authenticated") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-950/90 text-blue-300 border border-blue-700/60 shadow-sm">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
        LinkedIn Tab Active
      </span>
    );
  }
  if (norm === "youtube authenticated") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-950/90 text-purple-300 border border-purple-700/60 shadow-sm">
        <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
        YouTube Tab Active
      </span>
    );
  }
  if (isActive || norm === "browser launched" || norm.includes("cloud chromium")) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-cyan-950/90 text-cyan-300 border border-cyan-700/60 shadow-sm">
        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
        {norm.includes("cloud") ? "Cloud Chromium Standby" : "Chrome Connected (CDP :9222)"}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-900 text-slate-400 border border-slate-700">
      <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
      Local Agent Offline (Run start_agent.bat)
    </span>
  );
}

const SAMPLE_PROMPTS = [
  "Search SaaS Podcast and tech podcast for me and show me what results is it giving",
  "Find professional real estate podcasts on LinkedIn, prioritize recent video posts, identify hosts, find original channels, and locate business emails.",
  "Search AI startup podcasts, identify hosts, and locate business emails.",
  "Show me the research completed so far.",
  "Export all verified podcast leads to Excel.",
  "Download only leads with business emails.",
];

export default function AgentWorkspacePage() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [command, setCommand] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shotTick, setShotTick] = useState(0);
  const [showSetupGuide, setShowSetupGuide] = useState(false);

  const inFlightRef = useRef(false);
  const lastShotRef = useRef(0);

  const loadStatus = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const data = await apiFetch<AgentStatus>("/api/v1/agent/status");
      setStatus(data);
      const now = Date.now();
      // Throttle live screenshot re-rendering to at most once every 3.5s to prevent browser UI lag
      if (now - lastShotRef.current > 3500) {
        lastShotRef.current = now;
        setShotTick((t) => t + 1);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend not reachable");
    } finally {
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const timer = setInterval(loadStatus, 4000);
    let es: EventSource | null = null;
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    try {
      const base = getApiBase();
      es = new EventSource(`${base}/api/v1/agent/events`);
      es.onmessage = () => {
        // Debounce SSE updates so rapid log bursts trigger only 1 status poll
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          loadStatus();
        }, 1500);
      };
      es.onerror = () => {
        // Suppress noisy network errors during cold-start spin-ups
      };
    } catch {
      // EventSource fallback to interval polling
    }
    return () => {
      clearInterval(timer);
      if (debounceTimer) clearTimeout(debounceTimer);
      if (es) es.close();
    };
  }, [loadStatus]);

  async function sendCommand(text?: string) {
    const payload = (text ?? command).trim();
    if (!payload) return;
    setBusy(true);
    try {
      await apiFetch("/api/v1/agent/command", {
        method: "POST",
        body: JSON.stringify({ command: payload }),
      });
      if (!text) setCommand("");
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed sending command");
    } finally {
      setBusy(false);
    }
  }

  async function triggerControl(action: "pause" | "resume" | "stop") {
    setBusy(true);
    try {
      await apiFetch(`/api/v1/agent/${action}`, { method: "POST" });
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Control failed");
    } finally {
      setBusy(false);
    }
  }

  const task = status?.active_task;
  const stats = status?.stats;
  const recentLeads = status?.recent_leads || [];

  return (
    <div className="space-y-6 pb-12">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
            <Bot className="w-6 h-6 text-cyan-400" />
            Jarvis Agent Workspace
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Autonomous Real Estate Podcast Research Agent &bull; Controls desktop Chrome via CDP &bull; Saves leads to Neon PostgreSQL
          </p>
        </div>

        <div className="flex items-center gap-2">
          <StatusBadge status={status?.agent_state || "idle"} />
          <button
            type="button"
            disabled={busy || status?.agent_state === "running"}
            onClick={() =>
              sendCommand(
                "Find professional real estate podcasts on LinkedIn, prioritize recent video posts, identify hosts, find original YouTube channels, research their companies, and locate business emails."
              )
            }
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-medium cursor-pointer shadow-sm transition-all"
          >
            <Play className="w-4 h-4 fill-white" /> Start Research
          </button>
          <button
            type="button"
            disabled={busy || status?.agent_state !== "running"}
            onClick={() => triggerControl("pause")}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 border border-slate-700 text-slate-200 text-sm font-medium cursor-pointer transition-all"
          >
            <Pause className="w-4 h-4" /> Pause
          </button>
          <button
            type="button"
            disabled={busy || status?.agent_state !== "paused"}
            onClick={() => triggerControl("resume")}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 border border-slate-700 text-slate-200 text-sm font-medium cursor-pointer transition-all"
          >
            <RotateCcw className="w-4 h-4" /> Resume
          </button>
          <button
            type="button"
            disabled={busy || status?.agent_state === "idle"}
            onClick={() => triggerControl("stop")}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-rose-900/70 hover:bg-rose-800 disabled:opacity-40 border border-rose-700/60 text-rose-100 text-sm font-medium cursor-pointer transition-all"
          >
            <Square className="w-4 h-4 fill-rose-200" /> Stop
          </button>
        </div>
      </div>

      {error && (
        error.includes("waking up") || error.includes("spin-up") || error.includes("synchronizing") ? (
          <div className="p-3.5 rounded-lg bg-amber-950/70 border border-amber-700/80 text-amber-200 text-sm flex flex-wrap items-center justify-between gap-3 shadow-lg">
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping shrink-0" />
              <span>
                <strong>Cloud Service Waking Up:</strong> Render free-tier container is spinning up (~40s cold start). Automatically synchronizing leads and research status...
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-amber-300 font-mono animate-pulse">Auto-retrying...</span>
              <button
                type="button"
                onClick={() => loadStatus()}
                className="px-2.5 py-1 text-xs rounded bg-amber-900/80 hover:bg-amber-800 border border-amber-600/60 text-amber-100 cursor-pointer transition-colors"
              >
                Retry Now
              </button>
            </div>
          </div>
        ) : (
          <div className="p-3.5 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-sm flex flex-wrap items-center justify-between gap-3 shadow-lg">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse shrink-0" />
              <span>
                <strong>Backend Connection Notice:</strong> {error}
              </span>
            </div>
            <button
              type="button"
              onClick={() => loadStatus()}
              className="px-2.5 py-1 text-xs rounded bg-rose-900/80 hover:bg-rose-800 border border-rose-700/60 text-rose-100 cursor-pointer transition-colors"
            >
              Retry Connection
            </button>
          </div>
        )
      )}

      {/* Real-time Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-400">Qualified Podcasts</div>
            <div className="text-2xl font-bold text-white mt-1">{stats?.qualified_podcasts ?? 0}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-cyan-950/60 border border-cyan-800/50 flex items-center justify-center text-cyan-400">
            <Mic className="w-5 h-5" />
          </div>
        </div>

        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-400">Hosts Identified</div>
            <div className="text-2xl font-bold text-white mt-1">{stats?.hosts_identified ?? 0}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-emerald-950/60 border border-emerald-800/50 flex items-center justify-center text-emerald-400">
            <UserCheck className="w-5 h-5" />
          </div>
        </div>

        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-400">Emails Discovered</div>
            <div className="text-2xl font-bold text-white mt-1">{stats?.emails_discovered ?? 0}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-purple-950/60 border border-purple-800/50 flex items-center justify-center text-purple-400">
            <Mail className="w-5 h-5" />
          </div>
        </div>

        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-400">Neon DB Records</div>
            <div className="text-2xl font-bold text-white mt-1">{stats?.total_research_tasks ?? 0} tasks</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-slate-800/60 border border-slate-700/50 flex items-center justify-center text-slate-300">
            <Database className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Task Progress & Browser Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 space-y-2">
          <div className="text-xs uppercase tracking-wider text-slate-400">Continuous Task Status</div>
          <div className="flex items-center justify-between">
            <span className="font-semibold text-white truncate max-w-[280px]">
              {status?.agent_state === "running" && task
                ? `#${task.id} — ${task.search_keyword}`
                : "Standby — ready for instruction"}
            </span>
            <StatusBadge status={status?.agent_state || "idle"} />
          </div>
          <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-cyan-500 transition-all duration-300"
              style={{ width: `${status?.agent_state === "running" ? (task?.progress ?? 0) : 0}%` }}
            />
          </div>
          <div className="text-xs text-slate-400 flex items-center justify-between">
            <span>Stage: <strong className="text-slate-200">{status?.agent_state === "running" ? (task?.current_stage || "running") : "idle"}</strong></span>
            <span>{status?.agent_state === "running" ? (task?.progress ?? 0) : 0}%</span>
          </div>
        </div>

        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 space-y-3 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2">
            <div className="text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Globe className="w-3.5 h-3.5 text-cyan-400" /> Active Chrome Browser (Desktop CDP)
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowSetupGuide((v) => !v)}
                className="text-[11px] px-2.5 py-1 rounded border border-cyan-800/70 bg-cyan-950/50 text-cyan-300 hover:bg-cyan-900/60 cursor-pointer transition-all flex items-center gap-1.5 shadow-sm"
              >
                <Laptop className="w-3.5 h-3.5" />
                {status?.bridge_connected ? "Bridge Settings" : "Connect Local PC"}
              </button>
              {renderBrowserBadge(status?.browser_status, status?.browser_active, status?.bridge_connected, status?.device_name)}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="truncate text-xs text-cyan-300 font-mono flex-1 min-w-[200px]">
              {status?.current_url || "Chrome Standby — Ready. Click 'Start Research' or enter a chat command to begin."}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between text-xs text-slate-400 pt-1 border-t border-slate-800/40">
            <div>
              Active Website: <span className="text-slate-200 font-medium">{status?.current_website || "—"}</span>
            </div>
            <div className="text-[11px] text-slate-400 flex items-center gap-3">
              <span>Workspace: <strong className="text-cyan-300 font-mono">{status?.agency_id || "default"}</strong></span>
              <span>Desktop Chrome: <code className="text-cyan-300 font-mono">127.0.0.1:9222</code></span>
            </div>
          </div>
        </div>
      </div>

      {/* Multi-User Local Desktop Agent Setup Modal */}
      {showSetupGuide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-xl w-full p-6 shadow-2xl relative space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <Laptop className="w-5 h-5 text-cyan-400" />
                <h3 className="text-base font-semibold text-white">Connect Your Desktop Chrome</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowSetupGuide(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 cursor-pointer transition-all"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              YoursBuddy AI runs in multi-user mode. Anyone on the team can connect their own Windows computer to control their local Google Chrome browser from the cloud without exposing port 9222 publicly.
            </p>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 flex items-start gap-3">
                <span className="w-5 h-5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/80 flex items-center justify-center font-bold shrink-0">1</span>
                <div>
                  <div className="font-semibold text-slate-200">Start Desktop Chrome</div>
                  <div className="text-slate-400 mt-0.5">Double click <code className="text-cyan-300 font-mono">start_agent.bat</code> in the project folder, or run:</div>
                  <pre className="mt-1.5 p-2 bg-slate-900 rounded border border-slate-800 font-mono text-cyan-200 text-[11px] select-all overflow-x-auto">
                    chrome.exe --remote-debugging-port=9222 --user-data-dir=&quot;%LOCALAPPDATA%\Google\Chrome\AutomationData&quot;
                  </pre>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 flex items-start gap-3">
                <span className="w-5 h-5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/80 flex items-center justify-center font-bold shrink-0">2</span>
                <div>
                  <div className="font-semibold text-slate-200">Launch Bridge Agent</div>
                  <div className="text-slate-400 mt-0.5">The script initiates an outbound secure connection to Render for your workspace:</div>
                  <pre className="mt-1.5 p-2 bg-slate-900 rounded border border-slate-800 font-mono text-cyan-200 text-[11px] select-all overflow-x-auto">
                    {`python scripts\\local_agent.py --agency-id ${status?.agency_id || "default"}`}
                  </pre>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 flex items-start gap-3">
                <span className="w-5 h-5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800/80 flex items-center justify-center font-bold shrink-0">3</span>
                <div>
                  <div className="font-semibold text-slate-200">Autonomous Research Ready</div>
                  <div className="text-slate-400 mt-0.5">
                    Your badge will turn green (<strong className="text-emerald-400">Local Chrome Connected</strong>). Clicking &quot;Start Research&quot; will now operate your local browser window in real-time.
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={() => setShowSetupGuide(false)}
                className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium cursor-pointer transition-all"
              >
                Got It
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Split: Jarvis Console + Live Browser Viewer / Activity Log */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Conversation / Command Console */}
        <div className="rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col h-[520px]">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <span className="font-semibold text-white text-sm">Jarvis Command Console</span>
            <span className="text-xs text-slate-400">Real Estate Scope</span>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {(!status?.messages || status.messages.length === 0) && (
              <div className="text-sm text-slate-400 space-y-3">
                <p>Click &quot;Start Research&quot; or choose an instruction prompt below:</p>
                <div className="flex flex-wrap gap-2">
                  {SAMPLE_PROMPTS.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => sendCommand(p)}
                      className="text-left text-xs px-3 py-2 rounded-lg bg-slate-800/80 hover:bg-slate-800 border border-slate-700 text-slate-200 cursor-pointer transition-all"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {status?.messages.map((m) => (
              <div
                key={m.id}
                className={`p-3 rounded-lg text-sm ${
                  m.role === "user"
                    ? "bg-cyan-950/60 border border-cyan-800/50 ml-8 text-cyan-50"
                    : "bg-slate-800/70 border border-slate-700/70 mr-8 text-slate-100"
                }`}
              >
                <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1">
                  {m.role === "user" ? "You" : "YoursBuddy AI"}
                </div>
                <div className="whitespace-pre-wrap">{m.content}</div>
                {m.metadata_json?.download_url && (
                  <a
                    href={`${API_BASE}${m.metadata_json.download_url}`}
                    className="inline-block mt-2 text-xs font-medium text-emerald-300 underline"
                  >
                    Download Export File
                  </a>
                )}
              </div>
            ))}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendCommand();
            }}
            className="p-3 border-t border-slate-800 flex gap-2"
          >
            <input
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="Ask Jarvis to research podcasts, search YouTube, or export leads..."
              className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
            <button
              type="submit"
              disabled={busy || !command.trim()}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-medium cursor-pointer"
            >
              <Send className="w-4 h-4" /> Send
            </button>
          </form>
        </div>

        {/* Live Browser Viewer & Agent Activity */}
        <div className="space-y-4 flex flex-col h-[520px]">
          <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 flex-1 flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-white flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-400" /> Live Browser Viewer
              </span>
              <span className="text-[11px] text-slate-400">Desktop Chrome Stream</span>
            </div>
            <div className="text-[11px] bg-slate-950/70 border border-slate-800/80 text-cyan-300/90 rounded px-2.5 py-1.5 mb-2 flex items-center justify-between">
              <span>🖥️ <strong>Live Chrome Window:</strong> LinkedIn & YouTube open in separate tabs.</span>
              <span className="text-slate-400 text-[10px]">Sync tick: {shotTick}</span>
            </div>
            <div className="flex-1 rounded-lg bg-slate-950 border border-slate-800 overflow-hidden flex items-center justify-center min-h-[220px]">
              {status?.latest_screenshot_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`${API_BASE}${status.latest_screenshot_url}?t=${shotTick}`}
                  alt="Live desktop browser session"
                  className="max-h-full max-w-full object-contain rounded"
                />
              ) : (
                <div className="text-xs text-slate-500 text-center px-4">
                  Chrome session standby.<br />Click <strong>Start Research</strong> to begin automated discovery.
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 h-48 flex flex-col">
            <div className="text-sm font-semibold text-white flex items-center gap-2 mb-2">
              <Terminal className="w-4 h-4 text-emerald-400" /> Live Agent Activity
            </div>
            <div className="flex-1 overflow-y-auto space-y-1.5 font-mono text-xs">
              {(!status?.recent_logs || status.recent_logs.length === 0) && (
                <div className="text-slate-500">No activity logs recorded yet.</div>
              )}
              {status?.recent_logs.map((log) => (
                <div key={log.id} className="flex items-start gap-2 text-slate-300">
                  <span className="text-cyan-400 shrink-0 font-medium">[{log.stage}]</span>
                  <span className="break-words">{log.message}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Discovered Leads Table (Populates in Real Time) */}
      <div className="rounded-xl bg-slate-900/80 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="font-semibold text-white text-base">Discovered Real Estate Podcast Leads</h2>
            <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/60">
              {recentLeads.length} leads
            </span>
          </div>
          <div className="flex items-center gap-2">
            <ExportControls label="Export Leads" />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-950/80 text-xs uppercase text-slate-400 tracking-wider">
              <tr>
                <th className="px-4 py-3">Podcast Show</th>
                <th className="px-4 py-3">Host Name</th>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Business Email</th>
                <th className="px-4 py-3">Video Quality</th>
                <th className="px-4 py-3">Verification</th>
                <th className="px-4 py-3 text-right">Links</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {recentLeads.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    <p className="text-sm">No podcast leads discovered yet in this session.</p>
                    <p className="text-xs text-slate-500 mt-1">
                      Click <strong className="text-cyan-400">Start Research</strong> above &mdash; YoursBuddy will continuously search LinkedIn & YouTube, extract host emails, and populate this table in real time.
                    </p>
                  </td>
                </tr>
              ) : (
                recentLeads.map((r) => (
                  <tr key={r.lead_id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 font-medium text-white max-w-[200px] truncate">
                      {r.podcast_name}
                      {r.episode_title && (
                        <div className="text-[11px] text-slate-400 truncate font-normal">
                          {r.episode_title}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-200">
                      {r.host_full_name || <span className="text-slate-500 italic">Pending ID</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {r.host_company || <span className="text-slate-500">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      {r.business_email ? (
                        <span className="font-mono text-xs text-emerald-300 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/50">
                          {r.business_email}
                        </span>
                      ) : (
                        <span className="text-xs text-amber-400/80 italic">Searching...</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={r.qualification_status} />
                      {r.video_quality_score !== null && r.video_quality_score !== undefined && (
                        <span className="ml-1.5 text-xs text-slate-400 font-mono">
                          {r.video_quality_score}/100
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={r.identity_verification_status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1.5 justify-end">
                        {r.youtube_channel_url && (
                          <a
                            href={r.youtube_channel_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-red-400 transition-colors"
                            title="Open YouTube Channel"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                        {r.original_podcast_url && (
                          <a
                            href={r.original_podcast_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-cyan-300 transition-colors"
                            title="Open Original Source"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

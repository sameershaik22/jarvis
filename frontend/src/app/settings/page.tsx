"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

interface SafeSettings {
  openai_model: string;
  openai_configured: boolean;
  gemini_model: string;
  gemini_configured: boolean;
  tavily_configured: boolean;
  apollo_configured: boolean;
  n8n_configured: boolean;
  browser_headless: boolean;
  browser_channel: string;
  default_search_keyword: string;
  quality_threshold: number;
  max_posts_per_run: number;
  database_status: {
    configured: boolean;
    provider: string;
    host: string;
    connected: boolean;
    error: string | null;
  };
}

interface PlatformAuth {
  status: string;
  reason: string;
  last_checked?: string;
  url?: string | null;
}

interface AuthStatusResponse {
  linkedin: PlatformAuth;
  youtube: PlatformAuth;
}

function renderAuthBadge(status?: string) {
  const norm = (status || "").toLowerCase().replace(/_/g, " ").trim();
  if (norm === "logged in") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/90 text-emerald-400 border border-emerald-700/60 shadow-sm shadow-emerald-900/30">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Logged In
      </span>
    );
  }
  if (norm === "verification required") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-950/90 text-purple-300 border border-purple-700/60 shadow-sm shadow-purple-900/30">
        <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
        Verification Required
      </span>
    );
  }
  if (norm === "access restricted" || norm === "restricted") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-950/90 text-rose-400 border border-rose-700/60 shadow-sm shadow-rose-900/30">
        <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
        Access Restricted
      </span>
    );
  }
  if (norm === "connection error") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-950/50 text-rose-300 border border-rose-800/40">
        <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
        Connection Error
      </span>
    );
  }
  if (norm === "unknown") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-900 text-slate-400 border border-slate-700">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
        Unknown
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950/90 text-amber-400 border border-amber-700/60 shadow-sm shadow-amber-900/30">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
      Login Required
    </span>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SafeSettings | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  // Connected Accounts state
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [authMsg, setAuthMsg] = useState<string | null>(null);
  const [loadingAuth, setLoadingAuth] = useState(false);

  async function refreshAuthStatus() {
    setLoadingAuth(true);
    try {
      const data = await apiFetch<AuthStatusResponse>("/api/v1/auth/status");
      setAuthStatus(data);
    } catch (err: any) {
      console.warn("Failed to check auth status:", err);
    } finally {
      setLoadingAuth(false);
    }
  }

  useEffect(() => {
    apiFetch<SafeSettings>("/api/v1/settings").then(setSettings);
    refreshAuthStatus();
  }, []);

  async function handleConnect(platform: "linkedin" | "youtube") {
    setConnecting(platform);
    setAuthMsg(`Launching dedicated Chrome window for ${platform === "linkedin" ? "LinkedIn" : "YouTube"} login. Switch to the opened Chrome window on your desktop to log in.`);
    try {
      await apiFetch<any>(`/api/v1/auth/${platform}/connect`, { method: "POST" });
      setTimeout(refreshAuthStatus, 3000);
    } catch (err: any) {
      setAuthMsg(`Error launching browser: ${err.message}`);
    } finally {
      setConnecting(null);
    }
  }

  async function handleDisconnect(platform: "linkedin" | "youtube") {
    const name = platform === "linkedin" ? "LinkedIn" : "YouTube";
    if (!confirm(`Are you sure you want to disconnect and clear the saved session for ${name}?`)) {
      return;
    }
    try {
      await apiFetch<any>(`/api/v1/auth/${platform}/disconnect`, { method: "POST" });
      setAuthMsg(`${name} session disconnected and cleared.`);
      await refreshAuthStatus();
    } catch (err: any) {
      setAuthMsg(`Error disconnecting: ${err.message}`);
    }
  }

  async function handleResetSessions() {
    if (!confirm("Are you sure you want to reset ALL browser sessions? This will clear all cookies and cached session data in the dedicated browser profile.")) return;
    try {
      await apiFetch<any>("/api/v1/auth/session/reset", { method: "POST" });
      setAuthMsg("All browser sessions have been completely reset.");
      await refreshAuthStatus();
    } catch (err: any) {
      setAuthMsg(`Error resetting: ${err.message}`);
    }
  }

  function formatLastChecked(isoString?: string) {
    if (!isoString) return "Never";
    try {
      return new Date(isoString).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoString;
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!settings) return;
    const updated = await apiFetch<SafeSettings>("/api/v1/settings", {
      method: "PUT",
      body: JSON.stringify({
        openai_model: settings.openai_model,
        browser_headless: settings.browser_headless,
        browser_channel: settings.browser_channel,
        default_search_keyword: settings.default_search_keyword,
        quality_threshold: settings.quality_threshold,
        max_posts_per_run: settings.max_posts_per_run,
      }),
    });
    setSettings(updated);
    setSavedMsg("Settings saved.");
  }

  if (!settings) {
    return <div className="text-sm text-slate-400">Loading settings...</div>;
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-slate-400 mt-1">
          Configure AI model, Playwright browser options, quality thresholds, and inspect Neon PostgreSQL connection status. API keys and database credentials remain strictly server-side in .env.
        </p>
      </div>

      {/* Connected Accounts Section */}
      <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-6 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-white">Connected Accounts</h2>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-300">
                Dedicated Playwright Profile
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Manage the dedicated browser sessions used by Jarvis AI. Completely isolated from your everyday Chrome profile.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={refreshAuthStatus}
              disabled={loadingAuth}
              className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 cursor-pointer disabled:opacity-50 font-medium"
            >
              {loadingAuth ? "Checking..." : "Refresh Status"}
            </button>
            <button
              type="button"
              onClick={handleResetSessions}
              className="text-xs px-3 py-1.5 rounded-lg bg-rose-950/60 hover:bg-rose-900/80 text-rose-300 border border-rose-800/50 cursor-pointer font-medium"
            >
              Reset All Sessions
            </button>
          </div>
        </div>

        {/* Desktop Browser Instructions Banner */}
        <div className="p-3.5 rounded-xl bg-cyan-950/40 border border-cyan-800/50 text-xs text-cyan-200 space-y-1">
          <div className="font-semibold text-cyan-300 flex items-center gap-1.5">
            <span>ℹ️</span> Where to sign in:
          </div>
          <p className="text-[11px] leading-relaxed text-cyan-100/90">
            Clicking <strong>Connect</strong> opens a visible Chrome window directly on your desktop screen.
            Switch to that window, enter your login details, and complete any 2-factor verification yourself.
            Once logged in, click <strong>Check Status</strong> below to verify. Your credentials and cookies are stored securely inside the isolated profile (<code className="text-cyan-300">data/browser_profile</code>) and are never exposed.
          </p>
        </div>

        {authMsg && (
          <div className="p-3 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 flex items-center justify-between">
            <span>{authMsg}</span>
            <button
              type="button"
              onClick={() => setAuthMsg(null)}
              className="text-slate-400 hover:text-white text-xs ml-3"
            >
              ✕
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* LinkedIn Card */}
          <div className="p-5 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col justify-between space-y-4">
            <div className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400 font-bold text-sm">
                    in
                  </div>
                  <div>
                    <div className="font-semibold text-white text-sm">LinkedIn</div>
                    <div className="text-[11px] text-slate-400">Browser Authentication</div>
                  </div>
                </div>
                <div>{renderAuthBadge(authStatus?.linkedin?.status)}</div>
              </div>

              <div className="space-y-1.5 bg-slate-900/60 rounded-lg p-2.5 border border-slate-800/80 text-[11px]">
                <div className="text-slate-300 flex items-baseline justify-between">
                  <span className="text-slate-400">Status details:</span>
                  <span className="text-right text-slate-200 font-medium">
                    {authStatus?.linkedin?.reason || "Awaiting status check"}
                  </span>
                </div>
                <div className="text-slate-400 flex items-center justify-between">
                  <span>Last checked:</span>
                  <span className="text-slate-300 font-mono">
                    {formatLastChecked(authStatus?.linkedin?.last_checked)}
                  </span>
                </div>
              </div>

              <p className="text-xs text-slate-400 leading-relaxed">
                Enables discovery of real estate podcast video posts, creator updates, and host profile verification.
              </p>
            </div>

            <div className="space-y-2 pt-3 border-t border-slate-800/80">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={connecting === "linkedin"}
                  onClick={() => handleConnect("linkedin")}
                  className="flex-1 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold cursor-pointer transition-colors shadow-sm"
                >
                  {connecting === "linkedin"
                    ? "Launching Chrome..."
                    : authStatus?.linkedin?.status?.toLowerCase() === "logged in"
                    ? "Re-authenticate"
                    : "Connect LinkedIn"}
                </button>
                <button
                  type="button"
                  disabled={loadingAuth}
                  onClick={refreshAuthStatus}
                  className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
                  title="Check session status without navigating"
                >
                  Check Status
                </button>
              </div>

              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => handleDisconnect("linkedin")}
                  className="text-[11px] text-slate-400 hover:text-rose-400 cursor-pointer underline transition-colors"
                >
                  Disconnect & Clear LinkedIn Session
                </button>
              </div>
            </div>
          </div>

          {/* YouTube Card */}
          <div className="p-5 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col justify-between space-y-4">
            <div className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-lg bg-red-600/20 border border-red-500/40 flex items-center justify-center text-red-400 font-bold text-sm">
                    YT
                  </div>
                  <div>
                    <div className="font-semibold text-white text-sm">YouTube</div>
                    <div className="text-[11px] text-slate-400">Browser Authentication</div>
                  </div>
                </div>
                <div>{renderAuthBadge(authStatus?.youtube?.status)}</div>
              </div>

              <div className="space-y-1.5 bg-slate-900/60 rounded-lg p-2.5 border border-slate-800/80 text-[11px]">
                <div className="text-slate-300 flex items-baseline justify-between">
                  <span className="text-slate-400">Status details:</span>
                  <span className="text-right text-slate-200 font-medium">
                    {authStatus?.youtube?.reason || "Awaiting status check"}
                  </span>
                </div>
                <div className="text-slate-400 flex items-center justify-between">
                  <span>Last checked:</span>
                  <span className="text-slate-300 font-mono">
                    {formatLastChecked(authStatus?.youtube?.last_checked)}
                  </span>
                </div>
              </div>

              <p className="text-xs text-slate-400 leading-relaxed">
                Enables locating original podcast channels, full episode descriptions, and publicly listed business inquiry emails.
              </p>
            </div>

            <div className="space-y-2 pt-3 border-t border-slate-800/80">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={connecting === "youtube"}
                  onClick={() => handleConnect("youtube")}
                  className="flex-1 px-3 py-2 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-xs font-semibold cursor-pointer transition-colors shadow-sm"
                >
                  {connecting === "youtube"
                    ? "Launching Chrome..."
                    : authStatus?.youtube?.status?.toLowerCase() === "logged in"
                    ? "Re-authenticate"
                    : "Connect YouTube"}
                </button>
                <button
                  type="button"
                  disabled={loadingAuth}
                  onClick={refreshAuthStatus}
                  className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
                  title="Check session status without navigating"
                >
                  Check Status
                </button>
              </div>

              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => handleDisconnect("youtube")}
                  className="text-[11px] text-slate-400 hover:text-rose-400 cursor-pointer underline transition-colors"
                >
                  Disconnect & Clear YouTube Session
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Status Badges */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 space-y-1">
          <div className="text-xs uppercase text-slate-400">Database Connection</div>
          <div className="font-semibold text-white">{settings.database_status.provider}</div>
          <div className="text-xs text-slate-300">
            Host: {settings.database_status.host} •{" "}
            {settings.database_status.connected ? "Connected" : "Disconnected"}
          </div>
          {!settings.database_status.configured && (
            <div className="text-xs text-amber-300">
              Set DATABASE_URL in .env to connect your Neon PostgreSQL database.
            </div>
          )}
        </div>

        <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-4 space-y-1">
          <div className="text-xs uppercase text-slate-400">Approved Integrations (.env)</div>
          <div className="text-xs text-slate-200">
            Tavily AI Search: <strong>{settings.tavily_configured ? "Connected" : "Not Set"}</strong>
          </div>
          <div className="text-xs text-slate-200">
            Google Gemini: <strong>{settings.gemini_configured ? "Connected" : "Not Set"}</strong>
          </div>
          <div className="text-xs text-slate-200">
            OpenAI API: <strong>{settings.openai_configured ? "Configured" : "Optional / Not Set"}</strong>
          </div>
          <div className="text-xs text-slate-200">
            Apollo API: <strong>{settings.apollo_configured ? "Configured" : "Optional / Not Set"}</strong>
          </div>
          <div className="text-xs text-slate-200">
            n8n Cloud Webhook: <strong>{settings.n8n_configured ? "Configured" : "Not Set"}</strong>
          </div>
        </div>
      </div>

      <form onSubmit={save} className="rounded-xl bg-slate-900/80 border border-slate-800 p-6 space-y-4 text-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">OpenAI Model</label>
            <input
              value={settings.openai_model}
              onChange={(e) => setSettings({ ...settings, openai_model: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Default Search Keyword</label>
            <input
              value={settings.default_search_keyword}
              onChange={(e) => setSettings({ ...settings, default_search_keyword: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Video Quality Threshold (0–100)</label>
            <input
              type="number"
              min={0}
              max={100}
              value={settings.quality_threshold}
              onChange={(e) => setSettings({ ...settings, quality_threshold: Number(e.target.value) })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Max Posts Per Run (1–50)</label>
            <input
              type="number"
              min={1}
              max={50}
              value={settings.max_posts_per_run}
              onChange={(e) => setSettings({ ...settings, max_posts_per_run: Number(e.target.value) })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Browser Channel</label>
            <select
              value={settings.browser_channel}
              onChange={(e) => setSettings({ ...settings, browser_channel: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="chrome">Google Chrome</option>
              <option value="msedge">Microsoft Edge</option>
            </select>
          </div>

          <div className="flex items-center gap-2 pt-5">
            <input
              id="headless-toggle"
              type="checkbox"
              checked={settings.browser_headless}
              onChange={(e) => setSettings({ ...settings, browser_headless: e.target.checked })}
            />
            <label htmlFor="headless-toggle" className="text-slate-200">
              Run Browser Headless (keep unchecked for LinkedIn sign-in)
            </label>
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium cursor-pointer"
          >
            Save Configuration
          </button>
          {savedMsg && <span className="text-emerald-300 text-xs">{savedMsg}</span>}
        </div>
      </form>
    </div>
  );
}


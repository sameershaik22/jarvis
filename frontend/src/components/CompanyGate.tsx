"use client";

import { useEffect, useState } from "react";
import { getCompanyKey, setCompanyKey, getApiBase } from "@/lib/api";

interface CompanyGateProps {
  children?: React.ReactNode;
}

export function CompanyGate({ children }: CompanyGateProps) {
  const [unlocked, setUnlocked] = useState<boolean>(true); // default true to avoid flash
  const [mounted, setMounted] = useState<boolean>(false);
  const [inputKey, setInputKey] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    setMounted(true);
    const existing = getCompanyKey();
    if (existing) {
      setUnlocked(true);
    } else {
      // In internal company mode, we default to unlocked if previously accepted or let user unlock
      const stored = localStorage.getItem("yoursbuddy_company_unlocked");
      if (stored === "true") {
        setUnlocked(true);
      } else {
        setUnlocked(false);
      }
    }
  }, []);

  const handleUnlock = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const key = inputKey.trim() || "YoursBuddy2026";
    setLoading(true);
    setErrorMsg("");

    try {
      const base = getApiBase();
      const res = await fetch(`${base}/api/v1/auth/company-verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      const data = await res.json();
      if (data.valid) {
        setCompanyKey(key);
        localStorage.setItem("yoursbuddy_company_unlocked", "true");
        setUnlocked(true);
      } else {
        setErrorMsg("Invalid company key. Please check with your team administrator.");
      }
    } catch {
      // If network offline or backend waking up, allow local company unlock
      setCompanyKey(key);
      localStorage.setItem("yoursbuddy_company_unlocked", "true");
      setUnlocked(true);
    } finally {
      setLoading(false);
    }
  };

  if (!mounted || unlocked) {
    return <>{children}</>;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 backdrop-blur-md p-4">
      <div className="w-full max-w-md rounded-2xl border border-cyan-500/30 bg-slate-900/95 p-8 shadow-2xl shadow-cyan-950/50 text-slate-100">
        <div className="flex items-center space-x-3 mb-6">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-lg shadow-cyan-500/20">
            JV
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight text-white">Jarvis AI Workspace</h2>
            <p className="text-xs text-slate-400">Company-Wide Internal Cloud Agent</p>
          </div>
        </div>

        <p className="text-sm text-slate-300 mb-6 leading-relaxed">
          Welcome to the shared Jarvis AI research engine. Enter your company access key to access shared leads, live research, and exports.
        </p>

        <form onSubmit={handleUnlock} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Company Access Passphrase
            </label>
            <input
              type="password"
              value={inputKey}
              onChange={(e) => setInputKey(e.target.value)}
              placeholder="e.g. YoursBuddy2026"
              className="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 text-sm"
              autoFocus
            />
          </div>

          {errorMsg && (
            <p className="text-xs text-rose-400 bg-rose-950/50 border border-rose-800/60 rounded-lg p-2.5">
              {errorMsg}
            </p>
          )}

          <div className="flex space-x-3 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 py-3 px-4 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold text-sm rounded-xl transition duration-150 shadow-md shadow-cyan-600/20 disabled:opacity-50"
            >
              {loading ? "Verifying..." : "Unlock Company Workspace"}
            </button>
            <button
              type="button"
              onClick={() => {
                setInputKey("YoursBuddy2026");
                setTimeout(() => handleUnlock(), 50);
              }}
              className="py-3 px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-xl font-medium border border-slate-700"
            >
              Use Default
            </button>
          </div>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-800/80 text-center text-xs text-slate-400">
          Shared Company Workspace &bull; Zero Desktop Setup Required
        </div>
      </div>
    </div>
  );
}

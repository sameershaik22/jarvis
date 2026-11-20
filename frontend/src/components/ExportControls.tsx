"use client";

import { useState } from "react";
import { Download, FileSpreadsheet } from "lucide-react";
import { downloadExportFile, ExportFiltersPayload } from "@/lib/api";

export function ExportControls({
  filters = {},
  compact = false,
  label = "Export",
}: {
  filters?: ExportFiltersPayload;
  compact?: boolean;
  label?: string;
}) {
  const [loading, setLoading] = useState<"excel" | "csv" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function handleExport(fmt: "excel" | "csv") {
    try {
      setLoading(fmt);
      setNotice(null);
      const res = await downloadExportFile(fmt, filters);
      setNotice(`Downloaded ${res.filename} (${res.recordCount} records)`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Export failed");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={loading !== null}
          onClick={() => handleExport("excel")}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-60 text-white text-sm font-medium transition-colors cursor-pointer"
        >
          <FileSpreadsheet className="w-4 h-4" />
          <span>{loading === "excel" ? "Generating..." : compact ? "Excel (.xlsx)" : `${label} Excel`}</span>
        </button>
        <button
          type="button"
          disabled={loading !== null}
          onClick={() => handleExport("csv")}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 disabled:opacity-60 text-slate-100 text-sm font-medium transition-colors cursor-pointer"
        >
          <Download className="w-4 h-4" />
          <span>{loading === "csv" ? "Generating..." : compact ? "CSV (.csv)" : `${label} CSV`}</span>
        </button>
      </div>
      {notice && <span className="text-xs text-cyan-300">{notice}</span>}
    </div>
  );
}


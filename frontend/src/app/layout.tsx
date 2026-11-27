import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { CompanyGate } from "@/components/CompanyGate";

export const metadata: Metadata = {
  title: "Jarvis AI — Autonomous Podcast Research Agent",
  description:
    "Autonomous browser research agent for podcast discovery, host research, verification, and Excel/CSV reporting.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen flex bg-slate-950 text-slate-100 antialiased">
        <Sidebar />
        <main className="flex-1 min-w-0 overflow-y-auto p-6 lg:p-8">
          <CompanyGate>{children}</CompanyGate>
        </main>
      </body>
    </html>
  );
}


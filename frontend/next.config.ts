import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    const rawHost =
      process.env.INTERNAL_BACKEND_URL ||
      process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      "";

    const backendPort = process.env.BACKEND_PORT || "8000";
    let targetBackend = "http://127.0.0.1:8000";

    if (rawHost) {
      const trimmed = rawHost.trim();
      if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
        targetBackend = trimmed.replace(/\/$/, "");
      } else if (trimmed.includes(":")) {
        targetBackend = `http://${trimmed}`;
      } else {
        // Render internal private network hostname (e.g. javis-backend-3pfy)
        targetBackend = `http://${trimmed}:${backendPort}`;
      }
    }

    return [
      {
        source: "/api/:path*",
        destination: `${targetBackend}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

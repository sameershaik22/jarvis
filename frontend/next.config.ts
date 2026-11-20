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
      } else if (trimmed.includes(".onrender.com")) {
        targetBackend = `https://${trimmed}`;
      } else if (trimmed.includes("javis-backend")) {
        targetBackend = `https://javis-backend-3pfy.onrender.com`;
      } else if (trimmed.includes(":")) {
        targetBackend = `http://${trimmed}`;
      } else {
        // Fallback for Render or custom container
        targetBackend = `https://javis-backend-3pfy.onrender.com`;
      }
    } else if (process.env.NODE_ENV === "production") {
      targetBackend = "https://javis-backend-3pfy.onrender.com";
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

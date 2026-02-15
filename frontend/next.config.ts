import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Environment variable so the Next.js API route can reach the Python agent backend
  env: {
    AGENT_API_URL: process.env.AGENT_API_URL ?? "http://localhost:8000",
  },
}

export default nextConfig

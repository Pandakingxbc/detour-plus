import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/objects/:path*",
        destination: "http://localhost:8000/api/objects/:path*",
      },
    ]
  },
}

export default nextConfig

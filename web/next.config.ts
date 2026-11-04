import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Server actions default to 1 MB. Documents can be 10 MB, and the API enforces that limit.
  experimental: { serverActions: { bodySizeLimit: "11mb" } },
};

export default nextConfig;

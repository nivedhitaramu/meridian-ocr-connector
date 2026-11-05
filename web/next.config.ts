import path from "node:path";

import type { NextConfig } from "next";

// Browser tests swap Clerk for a stand-in, so they need no secrets. It only signs in to a test API that
// trusts the test issuer in e2e/, and normal builds never include it.
const browserTests = process.env.E2E_AUTH_STUB === "1";

const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  headers: async () => [{ source: "/:path*", headers: SECURITY_HEADERS }],
  // Server actions default to 1 MB. Documents can be 10 MB, and the API enforces that limit.
  experimental: { serverActions: { bodySizeLimit: "11mb" } },
  ...(browserTests
    ? {
        distDir: ".next-e2e",
        webpack: (config) => {
          config.resolve.alias["@clerk/nextjs/server$"] = path.resolve("e2e/clerk-stub/server.ts");
          config.resolve.alias["@clerk/nextjs$"] = path.resolve("e2e/clerk-stub/index.tsx");
          return config;
        },
      }
    : {}),
};

export default nextConfig;

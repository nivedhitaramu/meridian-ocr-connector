import os from "node:os";
import path from "node:path";

import { defineConfig } from "@playwright/test";

const PYTHON = process.env.E2E_PYTHON ?? "python";
const WORK = process.env.E2E_WORK_DIR ?? path.join(os.tmpdir(), `meridian-e2e-${Date.now()}`);
process.env.E2E_WORK_DIR = WORK;
const ISSUER = "http://127.0.0.1:9199";
const API = "http://127.0.0.1:8199";

export default defineConfig({
  testDir: "e2e",
  testMatch: "*.e2e.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 150_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:3199", trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    { command: `${PYTHON} web/e2e/servers/issuer.py`, cwd: "..", url: `${ISSUER}/.well-known/jwks.json`, reuseExistingServer: false },
    {
      command: `${PYTHON} web/e2e/servers/api.py`,
      cwd: "..",
      url: `${API}/healthz`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        CLERK_ISSUER: ISSUER,
        LLM_PROVIDER: "mock",
        DATABASE_URL: `sqlite:///${path.join(WORK, "e2e.db").replaceAll("\\", "/")}`,
        STORAGE_DIR: path.join(WORK, "files"),
        OTEL_CONSOLE_EXPORT: "0",
        PYTHONDONTWRITEBYTECODE: "1",
        E2E_WORK_DIR: WORK,
      },
    },
    {
      command: "npx next build && npx next start -p 3199 -H 127.0.0.1",
      url: "http://127.0.0.1:3199",
      timeout: 400_000,
      reuseExistingServer: false,
      env: {
        E2E_AUTH_STUB: "1",
        E2E_ISSUER: ISSUER,
        API_URL: API,
        NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_test_ZmljdGlvbmFsLmNsZXJrLmFjY291bnRzLmRldiQ=",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});

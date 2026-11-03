import "server-only";

import { auth } from "@clerk/nextjs/server";

import type { ApiContext } from "./api";

/** Runs on the server only, so the token and the API address never reach browser code. */
export async function apiContext(organizationId?: string): Promise<ApiContext> {
  const { getToken } = await auth();
  return {
    baseUrl: process.env.API_URL ?? "http://localhost:8000",
    token: await getToken(),
    organizationId,
  };
}

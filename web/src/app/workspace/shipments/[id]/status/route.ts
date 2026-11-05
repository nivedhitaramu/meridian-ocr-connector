import { NextResponse } from "next/server";

import { getJob } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

/** Lets the page ask whether a job is still running. It returns the status only, never results. */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const job = searchParams.get("job");
  if (!job) return NextResponse.json({ error: "Not found." }, { status: 404 });
  const { status } = await getJob(await apiContext(searchParams.get("org") ?? undefined), job);
  return NextResponse.json({ running: status === "queued" || status === "running" }, { headers: { "Cache-Control": "no-store" } });
}

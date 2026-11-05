import { NextResponse } from "next/server";

import { listIntake } from "@/lib/api";
import { apiContext } from "@/lib/server-api";

/** Lets the page ask whether a batch is still being read. It returns no document details. */
export async function GET(request: Request) {
  const org = new URL(request.url).searchParams.get("org") ?? undefined;
  const items = await listIntake(await apiContext(org));
  return NextResponse.json({ running: items.some((item) => item.status === "queued") }, { headers: { "Cache-Control": "no-store" } });
}

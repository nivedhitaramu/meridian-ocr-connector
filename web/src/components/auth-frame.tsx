import Link from "next/link";
import type { ReactNode } from "react";

export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-dvh flex-col items-center gap-8 px-4 py-10">
      <Link href="/" className="font-semibold tracking-tight">
        Meridian Intelligence
      </Link>
      {children}
    </main>
  );
}

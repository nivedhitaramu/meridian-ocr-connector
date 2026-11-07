import { UserButton } from "@clerk/nextjs";
import Link from "next/link";
import type { ReactNode } from "react";

import { LogoMark } from "@/components/landing/art";
import { NavLinks } from "@/components/nav-links";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-neutral-50 md:grid md:grid-cols-[16rem_minmax(0,1fr)] md:bg-[linear-gradient(to_right,#0a0a0a_16rem,#fafafa_16rem)]">
      <aside className="flex flex-col bg-neutral-950 text-white md:sticky md:top-0 md:h-dvh">
        <div className="flex items-center justify-between gap-3 px-5 py-5">
          <Link href="/" className="font-display flex items-center gap-2 text-lg font-extrabold tracking-tight">
            <LogoMark className="size-7 [&_rect:first-child]:fill-white [&_rect:last-child]:fill-white" />
            <span>
              MERIDIAN<span className="text-orange-500">.</span>
            </span>
          </Link>
          <div className="md:hidden">
            <UserButton />
          </div>
        </div>
        <NavLinks />
        <div className="m-3 hidden rounded-2xl bg-white/5 p-4 md:block">
          <p className="text-xs text-neutral-400">Synthetic documents only. Personal data is masked before any AI call.</p>
        </div>
        <div className="hidden border-t border-white/10 px-5 py-4 md:block [&_.cl-userButtonOuterIdentifier]:text-white">
          <UserButton showName />
        </div>
      </aside>
      <main className="mx-auto w-full max-w-6xl px-4 py-8 md:px-10 md:py-10">{children}</main>
    </div>
  );
}

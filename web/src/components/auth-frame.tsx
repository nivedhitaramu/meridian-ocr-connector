import { EyeOff, Scale, ScanLine } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { ContainerArt, LogoMark } from "@/components/landing/art";

const POINTS = [
  { icon: EyeOff, text: "Personal data masked before any AI call" },
  { icon: Scale, text: "Plain rules decide every status" },
  { icon: ScanLine, text: "Every check traced and auditable" },
];

/** Sign-in and sign-up: the home page's dark panel beside Clerk's form. */
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-dvh bg-white lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <aside className="relative hidden overflow-hidden bg-neutral-950 p-10 text-white lg:flex lg:flex-col">
        <Link href="/" className="font-display flex items-center gap-2 text-xl font-extrabold tracking-tight">
          <LogoMark className="size-8 [&_rect:first-child]:fill-white [&_rect:last-child]:fill-white" />
          <span>
            MERIDIAN<span className="text-orange-500">.</span>
          </span>
        </Link>
        <div className="mt-16 max-w-md">
          <p className="font-display text-4xl leading-tight font-semibold tracking-tight">
            Checking Your Cargo <span className="text-orange-400">Before Put-Away</span>
          </p>
          <ul className="mt-8 space-y-3">
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sm text-neutral-300">
                <span className="grid size-8 place-items-center rounded-lg bg-white/10">
                  <Icon aria-hidden className="size-4 text-orange-400" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        <ContainerArt className="mt-auto -mb-10 w-full max-w-lg self-end opacity-95" />
      </aside>
      <main className="flex flex-col items-center justify-center gap-8 px-4 py-10">
        <Link href="/" className="font-display flex items-center gap-2 text-xl font-extrabold tracking-tight lg:hidden">
          <LogoMark />
          <span>
            MERIDIAN<span className="text-orange-600">.</span>
          </span>
        </Link>
        {children}
        <p className="max-w-sm text-center text-xs text-neutral-600">
          A Team Delta project. Meridian Freight is fictional, and this demo uses synthetic documents only.
        </p>
      </main>
    </div>
  );
}

import { UserButton } from "@clerk/nextjs";
import { Activity, Building2, Inbox, KeyRound, LayoutDashboard, Package, Settings, TriangleAlert } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

// Only screens that exist. Later issues add theirs here.
const NAVIGATION = [
  { href: "/workspace", label: "Workspace", icon: Building2 },
  { href: "/workspace/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/workspace/intake", label: "Intake", icon: Inbox },
  { href: "/workspace/shipments", label: "Shipments", icon: Package },
  { href: "/workspace/exceptions", label: "Exceptions", icon: TriangleAlert },
  { href: "/workspace/observability", label: "Observability", icon: Activity },
  { href: "/workspace/settings", label: "Settings", icon: Settings },
  { href: "/workspace/api-access", label: "API access", icon: KeyRound },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border flex flex-col border-b md:border-r md:border-b-0">
        <div className="flex items-center justify-between gap-3 px-5 py-4">
          <Link href="/workspace" className="font-semibold tracking-tight">
            Meridian Intelligence
          </Link>
          <div className="md:hidden">
            <UserButton />
          </div>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:pb-0">
          {NAVIGATION.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="hover:bg-sidebar-accent hover:text-sidebar-accent-foreground flex items-center gap-2 rounded-md px-3 py-2 text-sm whitespace-nowrap"
            >
              <Icon aria-hidden className="size-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="hidden px-5 py-4 md:block">
          <UserButton showName />
        </div>
      </aside>
      <main className="mx-auto w-full max-w-5xl px-4 py-8 md:px-8">{children}</main>
    </div>
  );
}

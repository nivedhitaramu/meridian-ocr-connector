"use client";

import { Activity, Building2, Inbox, KeyRound, LayoutDashboard, Package, Settings, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

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

/** The current section is marked for screen readers too, not only by colour. */
export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:pb-0">
      {NAVIGATION.map(({ href, label, icon: Icon }) => {
        const current = href === "/workspace" ? pathname === href : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={current ? "page" : undefined}
            className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors ${
              current ? "bg-orange-500 text-neutral-950" : "text-neutral-300 hover:bg-white/10 hover:text-white"
            }`}
          >
            <Icon aria-hidden className={`size-4 ${current ? "" : "text-orange-400"}`} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

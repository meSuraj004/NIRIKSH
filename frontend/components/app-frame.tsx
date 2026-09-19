"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { getToken, authApi, type User } from "@/lib/api";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/inspections", label: "Inspections" },
  { href: "/inspections/new", label: "New Inspection" },
];

export default function AppFrame({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const init = setTimeout(() => {
      let cached: User | null = null;
      try {
        cached = JSON.parse(window.localStorage.getItem("niriksh_user") || "null");
      } catch {}
      setUser(cached);
      if (!getToken()) {
        router.replace("/login");
        return;
      }
      setReady(true);
    }, 0);
    return () => clearTimeout(init);
  }, [router]);

  if (!ready) {
    return <div className="min-h-screen bg-[#f4f6f9]" />;
  }

  return (
    <div className="min-h-screen bg-[#f4f6f9] text-slate-900">
      <div className="flex h-1.5">
        <div className="flex-1 bg-[#e87722]" />
        <div className="flex-1 bg-white" />
        <div className="flex-1 bg-[#1a7a3c]" />
      </div>
      <header className="border-b-2 border-[#12294a] bg-[#0f2a52] text-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center border-2 border-[#e87722] bg-white font-serif text-lg font-bold text-[#0f2a52]">
              N
            </span>
            <span>
              <span className="block font-serif text-xl font-bold tracking-wide">NIRIKSH</span>
              <span className="block text-[11px] uppercase tracking-widest text-[#b9c5da]">
                Legal Metrology Compliance System
              </span>
            </span>
          </Link>
          <nav className="ml-auto flex flex-wrap items-center gap-1">
            {navItems.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`border-b-[3px] px-3 py-2 text-sm font-medium transition ${
                    active
                      ? "border-[#e87722] text-white"
                      : "border-transparent text-[#b9c5da] hover:border-[#b9c5da] hover:text-white"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
            {user && (
              <div className="ml-3 flex items-center gap-3 border-l border-white/20 pl-3">
                <div className="hidden text-right sm:block">
                  <div className="text-sm font-medium">{user.full_name}</div>
                  <div className="text-[11px] uppercase tracking-wide text-[#e8a25c]">{user.role}</div>
                </div>
                <button
                  onClick={() => {
                    authApi.logout();
                    router.replace("/login");
                  }}
                  className="border border-white/30 px-3 py-1.5 text-sm text-white transition hover:bg-white/10"
                >
                  Logout
                </button>
              </div>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>
      <footer className="border-t border-[#d7dde6] bg-white py-4">
        <p className="text-center text-xs text-[#5b6472]">
          NIRIKSH &middot; Enforcement support under the Legal Metrology (Packaged Commodities)
          Rules, 2011
        </p>
      </footer>
    </div>
  );
}

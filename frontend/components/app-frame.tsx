"use client";

import { useEffect } from "react";
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

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  if (!getToken()) return null;

  let user: User | null = null;
  try {
    user = JSON.parse(window.localStorage.getItem("niriksh_user") || "null");
  } catch {}

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-20">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold">
              N
            </span>
            <span className="text-lg font-semibold tracking-tight">NIRIKSH</span>
            <span className="hidden rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-400 sm:inline">
              Legal Metrology Compliance
            </span>
          </Link>
          <nav className="ml-auto flex items-center gap-1">
            {navItems.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    active
                      ? "bg-indigo-600/20 text-indigo-300"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
            {user && (
              <div className="ml-3 flex items-center gap-3 border-l border-slate-800 pl-3">
                <div className="hidden text-right sm:block">
                  <div className="text-sm font-medium">{user.full_name}</div>
                  <div className="text-xs text-slate-500">{user.role}</div>
                </div>
                <button
                  onClick={() => {
                    authApi.logout();
                    router.replace("/login");
                  }}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
                >
                  Logout
                </button>
              </div>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { inspectionApi, rulesApi, type Inspection, type Rule } from "@/lib/api";
import { StatusBadge } from "@/components/badges";

export default function DashboardPage() {
  const [inspections, setInspections] = useState<Inspection[] | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([inspectionApi.list(), rulesApi.list().catch(() => [])])
      .then(([insp, rls]) => {
        setInspections(insp);
        setRules(rls);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  const count = (s: string) => inspections?.filter((i) => i.status === s).length ?? 0;
  const stats = [
    { label: "Total inspections", value: inspections?.length ?? 0, accent: "text-white" },
    { label: "Completed", value: count("COMPLETED"), accent: "text-emerald-300" },
    { label: "Processing", value: count("PROCESSING"), accent: "text-sky-300" },
    { label: "Needs attention", value: count("FAILED"), accent: "text-rose-300" },
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">
            Packaged commodity inspections under LMPC Rules, 2011
          </p>
        </div>
        <Link
          href="/inspections/new"
          className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
        >
          + New Inspection
        </Link>
      </div>

      {error && (
        <p className="rounded-lg bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}</p>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => (
          <div
            key={s.label}
            className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
          >
            <div className={`text-3xl font-semibold ${s.accent}`}>{s.value}</div>
            <div className="mt-1 text-sm text-slate-400">{s.label}</div>
          </div>
        ))}
      </div>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
              Recent inspections
            </h2>
            <Link href="/inspections" className="text-sm text-indigo-400 hover:text-indigo-300">
              View all →
            </Link>
          </div>
          {inspections === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : inspections.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-800 p-10 text-center">
              <p className="text-sm text-slate-400">No inspections yet.</p>
              <Link
                href="/inspections/new"
                className="mt-3 inline-block text-sm font-medium text-indigo-400 hover:text-indigo-300"
              >
                Create your first inspection →
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-slate-800 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
              {inspections.slice(0, 6).map((i) => (
                <li key={i.id}>
                  <Link
                    href={`/inspections/${i.id}`}
                    className="flex items-center gap-4 px-5 py-4 transition hover:bg-slate-800/40"
                  >
                    <span className="font-mono text-sm text-slate-500">
                      #{String(i.id).padStart(4, "0")}
                    </span>
                    <span className="flex-1 truncate text-sm">
                      {i.notes?.trim() || `Inspection ${i.id}`}
                    </span>
                    <StatusBadge status={i.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Active rulebook
          </h2>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <div className="text-3xl font-semibold text-white">{rules.length}</div>
            <div className="mt-1 text-sm text-slate-400">Statutory rules loaded</div>
            <ul className="mt-4 space-y-2">
              {rules.slice(0, 5).map((r) => (
                <li key={r.id} className="text-sm text-slate-300">
                  <span className="text-slate-500">{r.section_reference}</span> — {r.title}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}

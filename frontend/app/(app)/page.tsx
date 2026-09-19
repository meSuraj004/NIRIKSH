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
    { label: "Total inspections", value: inspections?.length ?? 0 },
    { label: "Completed", value: count("COMPLETED") },
    { label: "Processing", value: count("PROCESSING") },
    { label: "Needs attention", value: count("FAILED") },
  ];

  return (
    <div className="space-y-8">
      <div className="border-b-4 border-[#e87722] pb-4">
        <h1 className="font-serif text-2xl font-bold text-[#0f2a52]">Enforcement Dashboard</h1>
        <p className="mt-1 text-sm text-slate-600">
          Packaged commodity inspections under the Legal Metrology (Packaged Commodities) Rules, 2011
        </p>
      </div>

      {error && (
        <p className="border border-[#a02c2c]/30 bg-[#fbeaea] px-4 py-3 text-sm text-[#a02c2c]">{error}</p>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="border border-[#d7dde6] bg-white p-5 shadow-sm">
            <div className="font-serif text-3xl font-bold text-[#0f2a52]">{s.value}</div>
            <div className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-serif text-lg font-bold text-[#0f2a52]">Recent Inspections</h2>
            <Link href="/inspections" className="text-sm font-medium text-[#1e4f9c] hover:underline">
              View all →
            </Link>
          </div>
          {inspections === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : inspections.length === 0 ? (
            <div className="border border-dashed border-[#c9d1de] bg-white p-10 text-center">
              <p className="text-sm text-slate-600">No inspections recorded yet.</p>
              <Link
                href="/inspections/new"
                className="mt-3 inline-block bg-[#0f2a52] px-4 py-2 text-sm font-semibold text-white hover:bg-[#12294a]"
              >
                Create your first inspection
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-[#e3e8ef] border border-[#d7dde6] bg-white shadow-sm">
              {inspections.slice(0, 6).map((i) => (
                <li key={i.id}>
                  <Link
                    href={`/inspections/${i.id}`}
                    className="flex items-center gap-4 px-5 py-3.5 transition hover:bg-[#f4f6f9]"
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
          <h2 className="mb-3 font-serif text-lg font-bold text-[#0f2a52]">Active Rulebook</h2>
          <div className="border border-[#d7dde6] bg-white p-5 shadow-sm">
            <div className="font-serif text-3xl font-bold text-[#0f2a52]">{rules.length}</div>
            <div className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">
              Statutory rules loaded
            </div>
            <ul className="mt-4 space-y-2 border-t border-[#e3e8ef] pt-4">
              {rules.slice(0, 5).map((r) => (
                <li key={r.id} className="text-sm text-slate-700">
                  <span className="font-medium text-[#1e4f9c]">{r.section_reference}</span> — {r.title}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}

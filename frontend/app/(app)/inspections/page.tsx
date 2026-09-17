"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { inspectionApi, type Inspection } from "@/lib/api";
import { StatusBadge } from "@/components/badges";

export default function InspectionHistoryPage() {
  const [inspections, setInspections] = useState<Inspection[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    inspectionApi
      .list()
      .then(setInspections)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inspection history</h1>
          <p className="mt-1 text-sm text-slate-400">All recorded inspections, newest first</p>
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

      {inspections === null ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : inspections.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-800 p-12 text-center">
          <p className="text-sm text-slate-400">No inspections recorded yet.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-800/50 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-5 py-3 font-medium">ID</th>
                <th className="px-5 py-3 font-medium">Notes</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Product</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {inspections.map((i) => (
                <tr key={i.id} className="transition hover:bg-slate-800/40">
                  <td className="px-5 py-3.5 font-mono text-slate-400">
                    <Link href={`/inspections/${i.id}`} className="hover:text-indigo-300">
                      #{String(i.id).padStart(4, "0")}
                    </Link>
                  </td>
                  <td className="max-w-md truncate px-5 py-3.5">
                    <Link href={`/inspections/${i.id}`} className="hover:text-indigo-300">
                      {i.notes?.trim() || `Inspection ${i.id}`}
                    </Link>
                  </td>
                  <td className="px-5 py-3.5">
                    <StatusBadge status={i.status} />
                  </td>
                  <td className="px-5 py-3.5 text-slate-400">
                    {i.product_id ? `#${i.product_id}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

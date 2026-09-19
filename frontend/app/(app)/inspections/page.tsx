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
      <div className="flex flex-wrap items-end justify-between gap-4 border-b-4 border-[#e87722] pb-4">
        <div>
          <h1 className="font-serif text-2xl font-bold text-[#0f2a52]">Inspection History</h1>
          <p className="mt-1 text-sm text-slate-600">All recorded inspections, newest first</p>
        </div>
        <Link
          href="/inspections/new"
          className="bg-[#0f2a52] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#12294a]"
        >
          + New Inspection
        </Link>
      </div>

      {error && (
        <p className="border border-[#a02c2c]/30 bg-[#fbeaea] px-4 py-3 text-sm text-[#a02c2c]">{error}</p>
      )}

      {inspections === null ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : inspections.length === 0 ? (
        <div className="border border-dashed border-[#c9d1de] bg-white p-12 text-center text-sm text-slate-600">
          No inspections recorded yet.
        </div>
      ) : (
        <div className="overflow-x-auto border border-[#d7dde6] bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#0f2a52] text-xs uppercase tracking-wide text-white">
              <tr>
                <th className="px-5 py-3 font-semibold">ID</th>
                <th className="px-5 py-3 font-semibold">Notes</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 font-semibold">Product</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e3e8ef]">
              {inspections.map((i) => (
                <tr key={i.id} className="transition hover:bg-[#f4f6f9]">
                  <td className="px-5 py-3.5 font-mono text-slate-500">
                    <Link href={`/inspections/${i.id}`} className="hover:text-[#1e4f9c] hover:underline">
                      #{String(i.id).padStart(4, "0")}
                    </Link>
                  </td>
                  <td className="max-w-md truncate px-5 py-3.5">
                    <Link href={`/inspections/${i.id}`} className="hover:text-[#1e4f9c] hover:underline">
                      {i.notes?.trim() || `Inspection ${i.id}`}
                    </Link>
                  </td>
                  <td className="px-5 py-3.5">
                    <StatusBadge status={i.status} />
                  </td>
                  <td className="px-5 py-3.5 text-slate-500">
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

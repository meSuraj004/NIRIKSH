"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  inspectionApi,
  type Declaration,
  type InspectionDetail,
  type InspectionResults,
  type SubCheck,
} from "@/lib/api";
import { CheckBadge, DeclarationBadge, SeverityBadge, StatusBadge } from "@/components/badges";
import EvidenceImage from "@/components/evidence-image";

function prettyField(field: string): string {
  return field.split(".").slice(1).join(".").replace(/_/g, " ");
}

function sectionOf(field: string): string {
  return field.split(".")[0].replace(/_/g, " ");
}

export default function InspectionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [inspection, setInspection] = useState<InspectionDetail | null>(null);
  const [results, setResults] = useState<InspectionResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const detail = await inspectionApi.get(id);
      setInspection(detail);
      if (detail.status === "COMPLETED") {
        setResults(await inspectionApi.results(id));
        if (pollRef.current) clearInterval(pollRef.current);
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load inspection");
    }
  }, [id]);

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [load]);

  useEffect(() => {
    if (inspection?.status === "PROCESSING" && !pollRef.current) {
      pollRef.current = setInterval(load, 3000);
    }
    if (inspection && inspection.status !== "PROCESSING" && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [inspection, load]);

  async function startProcessing() {
    setBusy(true);
    try {
      await inspectionApi.process(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start processing");
    } finally {
      setBusy(false);
    }
  }

  if (error && !inspection) {
    return (
      <div className="rounded-xl bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {error} — <Link href="/inspections" className="underline">back to history</Link>
      </div>
    );
  }
  if (!inspection) return <p className="text-sm text-slate-500">Loading…</p>;

  const sections = new Map<string, Declaration[]>();
  results?.declarations.forEach((d) => {
    const key = sectionOf(d.field_name);
    if (!sections.has(key)) sections.set(key, []);
    sections.get(key)!.push(d);
  });

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/inspections" className="text-sm text-slate-500 hover:text-slate-300">
            ← Inspection history
          </Link>
          <h1 className="mt-1 flex items-center gap-3 text-2xl font-semibold tracking-tight">
            Inspection #{String(inspection.id).padStart(4, "0")}
            <StatusBadge status={inspection.status} />
          </h1>
          {inspection.notes && (
            <p className="mt-1 text-sm text-slate-400">{inspection.notes}</p>
          )}
        </div>
        {(inspection.status === "DRAFT" || inspection.status === "FAILED") && (
          <button
            onClick={startProcessing}
            disabled={busy || inspection.images.length === 0}
            className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {busy ? "Starting…" : inspection.status === "FAILED" ? "Retry processing" : "Start AI inspection"}
          </button>
        )}
      </div>

      {inspection.status === "FAILED" && inspection.error_message && (
        <div className="rounded-xl bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          Processing failed: {inspection.error_message}
        </div>
      )}

      {inspection.status === "PROCESSING" && (
        <div className="flex items-center gap-4 rounded-2xl border border-sky-500/20 bg-sky-500/5 px-6 py-8">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
          <div>
            <p className="font-medium text-sky-200">Running AI analysis…</p>
            <p className="text-sm text-slate-400">
              Preprocessing images → Vision OCR → declaration extraction → rule evaluation. This
              usually takes under a minute.
            </p>
          </div>
        </div>
      )}

      {inspection.status === "DRAFT" && inspection.images.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-800 p-10 text-center text-sm text-slate-400">
          No images uploaded yet.
        </div>
      )}

      {inspection.images.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Captured images ({inspection.images.length})
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {inspection.images.map((img) => (
              <div key={img.id} className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
                <EvidenceImage inspectionId={id} imageId={img.id} className="h-36 w-full object-cover" />
                <div className="truncate px-2.5 py-2 text-xs text-slate-500">
                  {img.original_filename || `image-${img.id}`}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {results && (
        <>
          {results.compliance_checks.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
                Compliance checks
              </h2>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {results.compliance_checks.map((c) => (
                  <div
                    key={c.parameter ?? c.findings}
                    className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold uppercase text-slate-300">
                        {c.parameter ?? "—"}
                      </span>
                      <CheckBadge status={c.status} />
                    </div>
                    {c.details?.section_reference && (
                      <p className="mt-0.5 text-xs text-slate-500">{c.details.section_reference}</p>
                    )}
                    <p className="mt-3 text-sm text-slate-300">{c.findings}</p>
                    {c.extracted_value && (
                      <p className="mt-2 text-xs text-slate-400">
                        Extracted: <span className="font-mono text-slate-300">{c.extracted_value}</span>
                      </p>
                    )}
                    {c.details?.sub_checks && c.details.sub_checks.length > 0 && (
                      <details className="mt-3">
                        <summary className="cursor-pointer text-xs text-indigo-400 hover:text-indigo-300">
                          {c.details.sub_checks.length} sub-checks
                        </summary>
                        <ul className="mt-2 space-y-2">
                          {c.details.sub_checks.map((sc: SubCheck) => (
                            <li key={sc.sub_check_id} className="rounded-lg bg-slate-800/50 p-2.5">
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-xs font-medium text-slate-200">{sc.name}</span>
                                <CheckBadge status={sc.status} />
                              </div>
                              <p className="mt-1 text-xs text-slate-400">{sc.details}</p>
                              {sc.remediation && (
                                <p className="mt-1 text-xs text-emerald-300/80">Fix: {sc.remediation}</p>
                              )}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.violations.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
                Violations ({results.violations.length})
              </h2>
              <ul className="space-y-3">
                {results.violations.map((v, i) => (
                  <li
                    key={v.error_code ?? i}
                    className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-5"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={v.severity} />
                      {v.error_code && (
                        <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300">
                          {v.error_code}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-sm text-slate-200">{v.description}</p>
                    {v.remediation && (
                      <p className="mt-1.5 text-sm text-emerald-300/80">Remediation: {v.remediation}</p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {results.declarations.length > 0 && (
            <section>
              <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-400">
                Extracted declarations
              </h2>
              <p className="mb-3 text-xs text-slate-500">
                Values the AI could not detect are shown as “Not detected” — never substituted.
              </p>
              <div className="space-y-5">
                {[...sections.entries()].map(([section, decls]) => (
                  <div
                    key={section}
                    className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60"
                  >
                    <div className="border-b border-slate-800 bg-slate-800/40 px-5 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      {section}
                    </div>
                    <ul className="divide-y divide-slate-800/70">
                      {decls.map((d) => (
                        <li key={d.field_name} className="flex items-center gap-4 px-5 py-3">
                          <div className="w-56 shrink-0">
                            <div className="text-sm text-slate-200">{prettyField(d.field_name)}</div>
                            {d.extraction_method && (
                              <div className="text-[11px] text-slate-600">{d.extraction_method}</div>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            {d.value ? (
                              <p className="break-words font-mono text-sm text-white">{d.value}</p>
                            ) : (
                              <p className="text-sm italic text-slate-600">Not detected</p>
                            )}
                          </div>
                          {d.source_image_id !== null && (
                            <EvidenceImage
                              inspectionId={id}
                              imageId={d.source_image_id}
                              alt={`Source for ${d.field_name}`}
                              className="h-11 w-11 shrink-0 rounded-lg object-cover ring-1 ring-slate-700"
                            />
                          )}
                          <div className="shrink-0">
                            <DeclarationBadge status={d.status} />
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.ocr_results.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
                Raw OCR evidence
              </h2>
              <div className="space-y-3">
                {results.ocr_results.map((r) => (
                  <details
                    key={r.image_id}
                    className="rounded-2xl border border-slate-800 bg-slate-900/60"
                  >
                    <summary className="cursor-pointer px-5 py-3 text-sm text-slate-300">
                      Image #{r.image_id} — {r.line_count ?? "?"} lines
                      {r.latency_sec !== null && ` · ${r.latency_sec}s`}
                      {r.model && <span className="text-xs text-slate-500"> · {r.model}</span>}
                    </summary>
                    <pre className="max-h-72 overflow-auto whitespace-pre-wrap border-t border-slate-800 px-5 py-4 text-xs text-slate-400">
                      {r.raw_text || "(no text detected)"}
                    </pre>
                  </details>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {inspection.status === "COMPLETED" && !results && !error && (
        <p className="text-sm text-slate-500">Loading results…</p>
      )}
    </div>
  );
}

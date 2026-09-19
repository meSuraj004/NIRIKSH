"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  inspectionApi,
  reportsApi,
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
  return field.split(".")[0].replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function InspectionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [inspection, setInspection] = useState<InspectionDetail | null>(null);
  const [results, setResults] = useState<InspectionResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
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
    const timer = setTimeout(load, 0);
    return () => {
      clearTimeout(timer);
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

  async function generateReport(format: "pdf" | "docx") {
    setReportError(null);
    setReportBusy(format);
    try {
      const meta = await reportsApi.generate(id, format);
      await reportsApi.download(meta.download_url, `niriksh-inspection-${id}.${format}`);
    } catch (e) {
      setReportError(e instanceof Error ? e.message : "Report generation failed");
    } finally {
      setReportBusy(null);
    }
  }

  if (error && !inspection) {
    return (
      <div className="border border-[#a02c2c]/30 bg-[#fbeaea] px-4 py-3 text-sm text-[#a02c2c]">
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
      <div className="flex flex-wrap items-start justify-between gap-4 border-b-4 border-[#e87722] pb-4">
        <div>
          <Link href="/inspections" className="text-sm font-medium text-[#1e4f9c] hover:underline">
            ← Inspection history
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-3 font-serif text-2xl font-bold text-[#0f2a52]">
            Inspection #{String(inspection.id).padStart(4, "0")}
            <StatusBadge status={inspection.status} />
          </h1>
          {inspection.notes && <p className="mt-1 text-sm text-slate-600">{inspection.notes}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {inspection.status === "COMPLETED" && (
            <>
              <button
                onClick={() => generateReport("pdf")}
                disabled={reportBusy !== null}
                className="bg-[#0f2a52] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#12294a] disabled:opacity-50"
              >
                {reportBusy === "pdf" ? "Generating…" : "Generate PDF Report"}
              </button>
              <button
                onClick={() => generateReport("docx")}
                disabled={reportBusy !== null}
                className="border border-[#0f2a52] px-4 py-2.5 text-sm font-semibold text-[#0f2a52] transition hover:bg-[#f4f6f9] disabled:opacity-50"
              >
                {reportBusy === "docx" ? "Preparing…" : "Download DOCX"}
              </button>
            </>
          )}
          {(inspection.status === "DRAFT" || inspection.status === "FAILED") && (
            <button
              onClick={startProcessing}
              disabled={busy || inspection.images.length === 0}
              className="bg-[#0f2a52] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#12294a] disabled:opacity-50"
            >
              {busy
                ? "Starting…"
                : inspection.status === "FAILED"
                  ? "Retry processing"
                  : "Start AI inspection"}
            </button>
          )}
        </div>
      </div>

      {reportError && (
        <p className="border border-[#a02c2c]/30 bg-[#fbeaea] px-4 py-3 text-sm text-[#a02c2c]">{reportError}</p>
      )}

      {inspection.status === "FAILED" && inspection.error_message && (
        <div className="border border-[#a02c2c]/30 bg-[#fbeaea] px-4 py-3 text-sm text-[#a02c2c]">
          Processing failed: {inspection.error_message}
        </div>
      )}

      {inspection.status === "PROCESSING" && (
        <div className="flex items-center gap-4 border border-[#1e4f9c]/30 bg-[#e8eefb] px-6 py-8">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#1e4f9c] border-t-transparent" />
          <div>
            <p className="font-semibold text-[#0f2a52]">Running AI analysis…</p>
            <p className="text-sm text-slate-600">
              Preprocessing images → Vision OCR → declaration extraction → rule evaluation. This
              usually takes under a minute.
            </p>
          </div>
        </div>
      )}

      {inspection.status === "DRAFT" && inspection.images.length === 0 && (
        <div className="border border-dashed border-[#c9d1de] bg-white p-10 text-center text-sm text-slate-600">
          No images uploaded yet.
        </div>
      )}

      {inspection.images.length > 0 && (
        <section>
          <h2 className="mb-3 font-serif text-lg font-bold text-[#0f2a52]">
            Captured images ({inspection.images.length})
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {inspection.images.map((img) => (
              <div key={img.id} className="border border-[#d7dde6] bg-white shadow-sm">
                <EvidenceImage inspectionId={id} imageId={img.id} className="h-36 w-full object-cover" />
                <div className="truncate border-t border-[#e3e8ef] px-2.5 py-2 text-xs text-slate-500">
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
              <h2 className="mb-3 font-serif text-lg font-bold text-[#0f2a52]">Compliance checks</h2>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {results.compliance_checks.map((c) => (
                  <div key={c.parameter ?? c.findings} className="border border-[#d7dde6] bg-white shadow-sm">
                    <div className="flex items-center justify-between gap-2 border-b border-[#e3e8ef] bg-[#f4f6f9] px-4 py-2.5">
                      <span className="text-sm font-semibold uppercase tracking-wide text-[#0f2a52]">
                        {c.parameter?.replace(/_/g, " ") ?? "—"}
                      </span>
                      <CheckBadge status={c.status} />
                    </div>
                    <div className="px-4 py-3">
                      {c.details?.section_reference && (
                        <p className="text-xs font-medium text-[#1e4f9c]">{c.details.section_reference}</p>
                      )}
                      <p className="mt-2 text-sm text-slate-700">{c.findings}</p>
                      {c.extracted_value && (
                        <p className="mt-2 text-xs text-slate-500">
                          Extracted:{" "}
                          <span className="font-mono text-slate-700">{c.extracted_value}</span>
                        </p>
                      )}
                      {c.details?.sub_checks && c.details.sub_checks.length > 0 && (
                        <details className="mt-3">
                          <summary className="cursor-pointer text-xs font-medium text-[#1e4f9c] hover:underline">
                            {c.details.sub_checks.length} sub-checks
                          </summary>
                          <ul className="mt-2 space-y-2">
                            {c.details.sub_checks.map((sc: SubCheck) => (
                              <li key={sc.sub_check_id} className="border border-[#e3e8ef] bg-[#f9fafc] p-2.5">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-xs font-semibold text-slate-800">{sc.name}</span>
                                  <CheckBadge status={sc.status} />
                                </div>
                                <p className="mt-1 text-xs text-slate-600">{sc.details}</p>
                                {sc.remediation && (
                                  <p className="mt-1 text-xs text-[#1a7a3c]">Fix: {sc.remediation}</p>
                                )}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.violations.length > 0 && (
            <section>
              <h2 className="mb-3 font-serif text-lg font-bold text-[#0f2a52]">
                Violations ({results.violations.length})
              </h2>
              <ul className="space-y-3">
                {results.violations.map((v, i) => (
                  <li key={v.error_code ?? i} className="border-l-4 border-[#a02c2c] bg-[#fbeaea] p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={v.severity} />
                      {v.error_code && (
                        <span className="bg-white px-2 py-0.5 font-mono text-xs text-slate-700 ring-1 ring-[#d7dde6]">
                          {v.error_code}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-sm text-slate-800">{v.description}</p>
                    {v.remediation && (
                      <p className="mt-1.5 text-sm text-[#1a7a3c]">Remediation: {v.remediation}</p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {results.declarations.length > 0 && (
            <section>
              <h2 className="font-serif text-lg font-bold text-[#0f2a52]">Extracted declarations</h2>
              <p className="mb-3 text-xs text-slate-500">
                Values that could not be detected are shown as “Not detected” — never substituted.
              </p>
              <div className="space-y-5">
                {[...sections.entries()].map(([section, decls]) => (
                  <div key={section} className="border border-[#d7dde6] bg-white shadow-sm">
                    <div className="border-b-2 border-[#0f2a52]/60 bg-[#f4f6f9] px-5 py-2.5 font-serif text-sm font-bold text-[#0f2a52]">
                      {section}
                    </div>
                    <ul className="divide-y divide-[#e3e8ef]">
                      {decls.map((d) => (
                        <li key={d.field_name} className="flex items-center gap-4 px-5 py-3">
                          <div className="w-52 shrink-0 text-sm text-slate-700">
                            {prettyField(d.field_name)}
                          </div>
                          <div className="min-w-0 flex-1">
                            {d.value ? (
                              <p className="break-words font-mono text-sm text-slate-900">{d.value}</p>
                            ) : (
                              <p className="text-sm italic text-slate-400">Not detected</p>
                            )}
                          </div>
                          {d.source_image_id !== null && (
                            <EvidenceImage
                              inspectionId={id}
                              imageId={d.source_image_id}
                              alt={`Source for ${d.field_name}`}
                              className="h-11 w-11 shrink-0 object-cover ring-1 ring-[#d7dde6]"
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
              <h2 className="mb-3 font-serif text-lg font-bold text-[#0f2a52]">Raw OCR evidence</h2>
              <div className="space-y-3">
                {results.ocr_results.map((r) => (
                  <details key={r.image_id} className="border border-[#d7dde6] bg-white shadow-sm">
                    <summary className="cursor-pointer px-5 py-3 text-sm text-slate-700">
                      Image #{r.image_id} — {r.line_count ?? "?"} lines
                      {r.latency_sec !== null && ` · ${r.latency_sec}s`}
                    </summary>
                    <pre className="max-h-72 overflow-auto whitespace-pre-wrap border-t border-[#e3e8ef] px-5 py-4 text-xs text-slate-600">
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

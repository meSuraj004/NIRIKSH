"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { inspectionApi, ApiError } from "@/lib/api";

const ACCEPTED = ["image/jpeg", "image/png", "image/webp", "image/bmp"];

export default function NewInspectionPage() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [notes, setNotes] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const valid: File[] = [];
    for (const f of Array.from(list)) {
      if (ACCEPTED.includes(f.type) && f.size <= 20 * 1024 * 1024) valid.push(f);
    }
    setFiles((prev) => [...prev, ...valid].slice(0, 8));
    setError(
      valid.length < list.length
        ? "Some files were skipped (only JPEG/PNG/WEBP/BMP up to 20 MB)"
        : null,
    );
  }

  async function start() {
    setError(null);
    if (files.length === 0) {
      setError("Add at least one product image before starting.");
      return;
    }
    setBusy(true);
    try {
      const inspection = await inspectionApi.create({ notes: notes.trim() || null });
      await inspectionApi.uploadImages(inspection.id, files);
      await inspectionApi.process(inspection.id);
      router.push(`/inspections/${inspection.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start inspection");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="border-b-4 border-[#e87722] pb-4">
        <h1 className="font-serif text-2xl font-bold text-[#0f2a52]">New Inspection</h1>
        <p className="mt-1 text-sm text-slate-600">
          Capture the front, back, and batch-stamp panels of the package. Multiple angles improve
          extraction accuracy.
        </p>
      </div>

      <div className="border border-[#d7dde6] bg-white p-6 shadow-sm">
        <label className="mb-1.5 block text-sm font-semibold text-[#0f2a52]">
          Inspection notes <span className="font-normal text-slate-500">(optional)</span>
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full border border-[#c9d1de] bg-white px-3 py-2 text-sm outline-none focus:border-[#1e4f9c] focus:ring-1 focus:ring-[#1e4f9c]"
          placeholder="e.g. Sweep #12 — Kirana store, aisle 3"
        />
      </div>

      <div className="border border-[#d7dde6] bg-white p-6 shadow-sm">
        <p className="mb-3 text-sm font-semibold text-[#0f2a52]">Product images</p>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          className="flex w-full flex-col items-center justify-center gap-2 border-2 border-dashed border-[#c9d1de] px-6 py-10 text-center transition hover:border-[#1e4f9c] hover:bg-[#f4f6f9]"
        >
          <span className="text-2xl">📦</span>
          <span className="text-sm font-medium text-slate-700">Click to add packaging photos</span>
          <span className="text-xs text-slate-500">JPEG, PNG, WEBP or BMP · up to 20 MB each</span>
        </button>
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPTED.join(",")}
          multiple
          className="hidden"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />

        {files.length > 0 && (
          <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {files.map((f, idx) => (
              <li key={`${f.name}-${idx}`} className="group relative border border-[#d7dde6] bg-white">
                <img src={URL.createObjectURL(f)} alt={f.name} className="h-28 w-full object-cover" />
                <button
                  onClick={() => setFiles(files.filter((_, i) => i !== idx))}
                  className="absolute right-1.5 top-1.5 bg-[#0f2a52] px-1.5 py-0.5 text-xs text-white opacity-0 transition group-hover:opacity-100"
                >
                  ✕
                </button>
                <div className="truncate border-t border-[#e3e8ef] px-2 py-1.5 text-xs text-slate-500">
                  {f.name}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <p className="border border-[#a02c2c]/30 bg-[#fbeaea] px-4 py-3 text-sm text-[#a02c2c]">{error}</p>
      )}

      <button
        onClick={start}
        disabled={busy}
        className="w-full bg-[#0f2a52] px-4 py-3 text-sm font-semibold uppercase tracking-wide text-white transition hover:bg-[#12294a] disabled:opacity-50"
      >
        {busy
          ? "Creating inspection…"
          : `Start AI inspection (${files.length} image${files.length === 1 ? "" : "s"})`}
      </button>
    </div>
  );
}

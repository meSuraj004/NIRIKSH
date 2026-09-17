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
      valid.length < list.length ? "Some files were skipped (only JPEG/PNG/WEBP/BMP up to 20 MB)" : null,
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
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New inspection</h1>
        <p className="mt-1 text-sm text-slate-400">
          Capture the front, back, and batch-stamp panels of the package. Multiple angles improve
          extraction accuracy.
        </p>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
        <label className="mb-1.5 block text-sm font-medium text-slate-300">
          Inspection notes <span className="text-slate-500">(optional)</span>
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
          placeholder="e.g. Sweep #12 — Kirana store, aisle 3"
        />
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
        <p className="mb-3 text-sm font-medium text-slate-300">Product images</p>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          className="flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-700 px-6 py-10 text-center transition hover:border-indigo-500/60 hover:bg-slate-800/30"
        >
          <span className="text-2xl">📦</span>
          <span className="text-sm font-medium text-slate-300">
            Click to add packaging photos
          </span>
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
              <li
                key={`${f.name}-${idx}`}
                className="group relative overflow-hidden rounded-lg border border-slate-700 bg-slate-800"
              >
                <img
                  src={URL.createObjectURL(f)}
                  alt={f.name}
                  className="h-28 w-full object-cover"
                />
                <button
                  onClick={() => setFiles(files.filter((_, i) => i !== idx))}
                  className="absolute right-1.5 top-1.5 rounded-md bg-slate-950/80 px-1.5 py-0.5 text-xs text-slate-300 opacity-0 transition group-hover:opacity-100 hover:text-rose-300"
                >
                  ✕
                </button>
                <div className="truncate px-2 py-1.5 text-xs text-slate-400">{f.name}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <p className="rounded-lg bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}</p>
      )}

      <button
        onClick={start}
        disabled={busy}
        className="w-full rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
      >
        {busy ? "Creating inspection…" : `Start AI inspection (${files.length} image${files.length === 1 ? "" : "s"})`}
      </button>
    </div>
  );
}

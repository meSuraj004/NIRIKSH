import type { CheckStatus, DeclarationStatus, InspectionStatus } from "@/lib/api";

const toneClasses: Record<string, string> = {
  PASSED: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  FAILED: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  REVIEW: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  NOT_APPLICABLE: "bg-slate-500/15 text-slate-400 ring-slate-500/30",
  DETECTED: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  NOT_DETECTED: "bg-slate-500/15 text-slate-400 ring-slate-500/30",
  UNCERTAIN: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  DRAFT: "bg-slate-500/15 text-slate-400 ring-slate-500/30",
  PROCESSING: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  COMPLETED: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  CRITICAL: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  MAJOR: "bg-orange-500/15 text-orange-300 ring-orange-500/30",
  WARNING: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
};

const labels: Record<string, string> = {
  PASSED: "PASS",
  FAILED: "FAIL",
  REVIEW: "REVIEW",
  NOT_APPLICABLE: "N/A",
  NOT_DETECTED: "Not detected",
  UNCERTAIN: "Uncertain",
  DETECTED: "Detected",
};

export function Badge({
  value,
  label,
}: {
  value: string;
  label?: string;
}) {
  const tone = toneClasses[value] ?? "bg-slate-500/15 text-slate-300 ring-slate-500/30";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset whitespace-nowrap ${tone}`}
    >
      {label ?? labels[value] ?? value}
    </span>
  );
}

export function StatusBadge({ status }: { status: InspectionStatus }) {
  return <Badge value={status} />;
}

export function CheckBadge({ status }: { status: CheckStatus }) {
  return <Badge value={status} />;
}

export function DeclarationBadge({ status }: { status: DeclarationStatus }) {
  return <Badge value={status} />;
}

export function SeverityBadge({ severity }: { severity: string | null }) {
  if (!severity) return null;
  return <Badge value={severity} label={severity} />;
}

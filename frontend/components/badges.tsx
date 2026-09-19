import type { CheckStatus, DeclarationStatus, InspectionStatus } from "@/lib/api";

const toneClasses: Record<string, string> = {
  PASSED: "bg-[#e7f2ea] text-[#1a7a3c] ring-[#1a7a3c]/40",
  FAILED: "bg-[#fbeaea] text-[#a02c2c] ring-[#a02c2c]/40",
  REVIEW: "bg-[#fdf3e4] text-[#b26a08] ring-[#b26a08]/40",
  NOT_APPLICABLE: "bg-[#eef1f6] text-[#5b6472] ring-[#5b6472]/30",
  DETECTED: "bg-[#e7f2ea] text-[#1a7a3c] ring-[#1a7a3c]/40",
  NOT_DETECTED: "bg-[#eef1f6] text-[#5b6472] ring-[#5b6472]/30",
  UNCERTAIN: "bg-[#fdf3e4] text-[#b26a08] ring-[#b26a08]/40",
  DRAFT: "bg-[#eef1f6] text-[#5b6472] ring-[#5b6472]/30",
  PROCESSING: "bg-[#e8eefb] text-[#1e4f9c] ring-[#1e4f9c]/40",
  COMPLETED: "bg-[#e7f2ea] text-[#1a7a3c] ring-[#1a7a3c]/40",
  CRITICAL: "bg-[#fbeaea] text-[#a02c2c] ring-[#a02c2c]/40",
  MAJOR: "bg-[#fdf3e4] text-[#b26a08] ring-[#b26a08]/40",
  WARNING: "bg-[#fdf3e4] text-[#b26a08] ring-[#b26a08]/40",
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

export function Badge({ value, label }: { value: string; label?: string }) {
  const tone = toneClasses[value] ?? "bg-[#eef1f6] text-[#0f2a52] ring-[#5b6472]/30";
  return (
    <span
      className={`inline-flex items-center rounded-sm px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1 ring-inset whitespace-nowrap ${tone}`}
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

"use client";

import { useEffect, useState } from "react";
import { fetchImageBlobUrl } from "@/lib/api";

export default function EvidenceImage({
  inspectionId,
  imageId,
  className,
  alt = "Evidence image",
}: {
  inspectionId: number;
  imageId: number | null;
  className?: string;
  alt?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (imageId === null) return;
    let cancelled = false;
    let url: string | null = null;
    fetchImageBlobUrl(inspectionId, imageId)
      .then((u) => {
        if (cancelled) URL.revokeObjectURL(u);
        else {
          url = u;
          setSrc(u);
        }
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [inspectionId, imageId]);

  if (imageId === null) {
    return (
      <div className={`flex items-center justify-center rounded-lg bg-slate-800/60 text-xs text-slate-500 ${className ?? ""}`}>
        no image
      </div>
    );
  }
  if (failed) {
    return (
      <div className={`flex items-center justify-center rounded-lg bg-slate-800/60 text-xs text-slate-500 ${className ?? ""}`}>
        unavailable
      </div>
    );
  }
  if (!src) {
    return <div className={`animate-pulse rounded-lg bg-slate-800 ${className ?? ""}`} />;
  }
  return <img src={src} alt={alt} className={className} />;
}

"use client";

import { useEffect } from "react";

/** A panel that slides up from the bottom (phone-first). Closes on the backdrop, the button or Escape. */
export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-black/50" />
      <div className="relative z-10 flex max-h-[85dvh] w-full max-w-[440px] flex-col gap-3 overflow-y-auto rounded-t-2xl border border-line bg-bg px-5 pb-6 pt-4" data-testid="sheet">
        <div className="flex items-center justify-between gap-3">
          <div className="font-display text-lg font-bold">{title}</div>
          <button type="button" onClick={onClose} className="rounded-full border border-line px-2.5 py-1 text-xs text-text2">Close</button>
        </div>
        {children}
      </div>
    </div>
  );
}

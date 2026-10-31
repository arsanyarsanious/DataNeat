"use client";
import type { CSSProperties } from "react";
import { Loader2, Paintbrush } from "lucide-react";

export function originalFillStyle(fill: string | null | undefined): CSSProperties | undefined {
  if (!fill || !/^#[0-9a-f]{6}$/i.test(fill)) return undefined;
  const rgb = [1, 3, 5].map(start => parseInt(fill.slice(start, start + 2), 16) / 255);
  const linear = rgb.map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  const luminance = .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
  return { backgroundColor: fill, color: (luminance + .05) / .05 >= 1.05 / (luminance + .05) ? "#000000" : "#ffffff" };
}

export function OriginalColorsControl({ enabled, busy, disabled, message, onToggle }: {
  enabled: boolean; busy: boolean; disabled?: boolean; message?: string; onToggle: () => void;
}) {
  return <button type="button" className="button ghost original-colors-toggle" aria-pressed={enabled} disabled={busy || disabled} title={message || "Show the original solid cell fills. This changes the view only."} onClick={onToggle}>
    {busy ? <Loader2 size={16} className="spin" aria-hidden="true"/> : <Paintbrush size={16} aria-hidden="true"/>}
    Show original colors
  </button>;
}

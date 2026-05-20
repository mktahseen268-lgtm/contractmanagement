"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// Lightweight, dependency-free SVG charts + a count-up hook. No chart library, no canvas — just
// inline SVG paths so they ship as part of the route bundle with zero extra weight. Draw-on
// animation via CSS (honors prefers-reduced-motion in globals.css).

// ---- count-up: animate a number from 0 → target on mount ----

export function useCountUp(target: number, durationMs = 700): number {
  const [value, setValue] = useState(0);
  const raf = useRef<number | null>(null);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + (target - from) * eased);
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [target, durationMs]);
  return value;
}

// ---- sparkline: tiny inline trend line with soft gradient fill ----

export function Sparkline({ data, stroke = "var(--color-accent)", className }: { data: number[]; stroke?: string; className?: string }) {
  if (!data.length) return null;
  const w = 100;
  const h = 28;
  const pad = 2;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1 || 1)) * (w - 2 * pad);
    const y = h - pad - ((v - min) / range) * (h - 2 * pad);
    return [x, y] as const;
  });
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)},${h} L${pts[0][0].toFixed(1)},${h} Z`;
  const gid = `spk-${Math.round(stroke.length * 7)}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={cn("h-7 w-full", className)} aria-hidden>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} className="chart-fade" />
      <path d={line} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="chart-draw" style={{ ["--dash" as string]: "240" }} />
    </svg>
  );
}

// ---- area chart: the featured, interactive trend (hover shows the week's count + value) ----

export type TrendPoint = { label: string; contracts: number; value: number };

export function AreaChart({ points, formatValue }: { points: TrendPoint[]; formatValue?: (v: number) => string }) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  if (!points.length) return null;

  const w = 640;
  const h = 180;
  const padX = 10;
  const padTop = 16;
  const padBottom = 26;
  const max = Math.max(...points.map((p) => p.contracts), 1);

  const coords = points.map((p, i) => {
    const x = padX + (i / (points.length - 1 || 1)) * (w - 2 * padX);
    const y = padTop + (1 - p.contracts / max) * (h - padTop - padBottom);
    return { x, y };
  });
  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const baseY = h - padBottom;
  const area = `${line} L${coords[coords.length - 1].x.toFixed(1)},${baseY} L${coords[0].x.toFixed(1)},${baseY} Z`;

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const relX = ((e.clientX - rect.left) / rect.width) * w;
    // nearest point index
    let best = 0;
    let bestD = Infinity;
    coords.forEach((c, i) => {
      const d = Math.abs(c.x - relX);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    setHover(best);
  }

  const hp = hover != null ? coords[hover] : null;
  const hpData = hover != null ? points[hover] : null;

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${w} ${h}`}
        className="h-44 w-full"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Contracts created per week, last 8 weeks"
      >
        <defs>
          <linearGradient id="area-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* faint baseline */}
        <line x1={padX} y1={baseY} x2={w - padX} y2={baseY} stroke="var(--color-border)" strokeWidth="1" />
        <path d={area} fill="url(#area-grad)" className="chart-fade" />
        <path d={line} fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="chart-draw" style={{ ["--dash" as string]: "1400" }} />
        {/* point dots */}
        {coords.map((c, i) => (
          <circle key={i} cx={c.x} cy={c.y} r={hover === i ? 4 : 2.5} fill="var(--color-accent)" className="transition-all" />
        ))}
        {/* hover guide */}
        {hp && <line x1={hp.x} y1={padTop} x2={hp.x} y2={baseY} stroke="var(--color-accent)" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />}
        {/* x labels (every other to avoid crowding) */}
        {points.map((p, i) =>
          i % 2 === 0 ? (
            <text key={i} x={coords[i].x} y={h - 8} textAnchor="middle" className="fill-ink-3" style={{ fontSize: 9 }}>
              {p.label}
            </text>
          ) : null,
        )}
      </svg>
      {/* tooltip */}
      {hp && hpData && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 rounded-lg border border-line bg-white px-2.5 py-1.5 text-xs shadow-pop"
          style={{ left: `${(hp.x / w) * 100}%`, top: 0 }}
        >
          <div className="font-semibold text-ink">{hpData.contracts} contract{hpData.contracts === 1 ? "" : "s"}</div>
          <div className="text-ink-3">{hpData.label}{formatValue ? ` · ${formatValue(hpData.value)}` : ""}</div>
        </div>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";

type YearCount = { year: number; count: number };

const W = 640;
const H = 220;
const PAD = { top: 24, right: 8, bottom: 24, left: 32 };

// 目盛りをきりの良い数にする（1, 2, 5, 10, 20, ...）
function niceStep(max: number) {
  const raw = max / 4;
  const pow = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? raw;
}

export default function YearChart({ data }: { data: YearCount[] }) {
  const [active, setActive] = useState<number | null>(null);
  if (data.length === 0) return <p className="text-sm text-zinc-500">まだ論文がありません。</p>;

  // 論文の無い年も 0 件として並べる（年が飛ぶと間隔が嘘になる）
  const first = data[0].year;
  const last = data[data.length - 1].year;
  const years: YearCount[] = [];
  for (let y = first; y <= last; y++) {
    years.push({ year: y, count: data.find((d) => d.year === y)?.count ?? 0 });
  }

  const maxCount = Math.max(...years.map((d) => d.count));
  const step = niceStep(maxCount);
  const top = Math.ceil(maxCount / step) * step;
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step);

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const band = plotW / years.length;
  const barW = Math.min(24, band * 0.6);
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;
  const peak = years.reduce((a, b) => (b.count > a.count ? b : a));
  const activeYear = years.find((d) => d.year === active);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="公開年ごとの論文数">
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(t)}
              y2={y(t)}
              stroke={t === 0 ? "var(--viz-axis)" : "var(--viz-grid)"}
              strokeWidth={1}
            />
            <text
              x={PAD.left - 6}
              y={y(t)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--viz-muted)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {t}
            </text>
          </g>
        ))}

        {years.map((d, i) => {
          const cx = PAD.left + band * i + band / 2;
          const h = y(0) - y(d.count);
          const r = Math.min(4, h);
          const x0 = cx - barW / 2;
          const x1 = cx + barW / 2;
          // 上の角だけ丸め、根元（基準線側）は四角のまま
          const path =
            h > 0
              ? `M${x0},${y(0)} V${y(d.count) + r} Q${x0},${y(d.count)} ${x0 + r},${y(d.count)} H${x1 - r} Q${x1},${y(d.count)} ${x1},${y(d.count) + r} V${y(0)} Z`
              : "";
          return (
            <g
              key={d.year}
              tabIndex={0}
              onPointerEnter={() => setActive(d.year)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(d.year)}
              onBlur={() => setActive(null)}
              className="outline-none"
              aria-label={`${d.year}年 ${d.count}本`}
            >
              {/* 当たり判定は棒より広く、帯全体にする */}
              <rect x={PAD.left + band * i} y={PAD.top} width={band} height={plotH} fill="transparent" />
              {path && (
                <path
                  d={path}
                  fill="var(--viz-mark)"
                  opacity={active === null || active === d.year ? 1 : 0.45}
                />
              )}
              {d.year === peak.year && (
                <text x={cx} y={y(d.count) - 6} textAnchor="middle" fontSize={11} fill="var(--viz-ink-2)">
                  {d.count}
                </text>
              )}
              <text x={cx} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--viz-muted)">
                {years.length > 12 && i % 2 === 1 ? "" : `'${String(d.year).slice(2)}`}
              </text>
            </g>
          );
        })}
      </svg>

      {activeYear && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 rounded border border-zinc-200 bg-white px-2 py-1 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900"
          style={{
            left: `${((PAD.left + band * years.indexOf(activeYear) + band / 2) / W) * 100}%`,
            top: 0,
          }}
        >
          <span className="font-semibold">{activeYear.count} 本</span>
          <span className="ml-1 text-zinc-500">{activeYear.year}年</span>
        </div>
      )}
    </div>
  );
}

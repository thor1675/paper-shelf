"use client";

import { useState } from "react";

// short は横軸に出す短い表記（"2024年" → "'24" など）。サーバから関数は渡せないので、値で受け取る
type Bar = { label: string; short: string; count: number };

const W = 640;
const H = 220;
const PAD = { top: 24, right: 8, bottom: 24, left: 32 };

// 目盛りをきりの良い数にする（1, 2, 5, 10, 20, ...）
function niceStep(max: number) {
  const raw = max / 4;
  const pow = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? raw;
}

// 縦棒グラフ。棒の並びと抜けの埋め方（年や月）は呼ぶ側で決める
export default function BarChart({
  data,
  ariaLabel,
}: {
  data: Bar[];
  ariaLabel: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  if (data.length === 0) return <p className="text-sm text-zinc-500">まだ論文がありません</p>;

  const years = data;

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
  const activeYear = active === null ? undefined : years[active];

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="group" aria-label={ariaLabel}>
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
              key={d.label}
              tabIndex={0}
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
              className="viz-focus outline-none"
              aria-label={`${d.label} ${d.count}本`}
            >
              {/* 当たり判定は棒より広く、帯全体にする */}
              <rect x={PAD.left + band * i} y={PAD.top} width={band} height={plotH} fill="transparent" />
              {path && (
                <path
                  d={path}
                  className="viz-mark"
                  fill="var(--viz-mark)"
                  opacity={active === null || active === i ? 1 : 0.45}
                />
              )}
              {/* 一番多い年だけ数を出す。触れている間はツールチップと重なるので隠す */}
              {d === peak && active === null && (
                <text x={cx} y={y(d.count) - 6} textAnchor="middle" fontSize={11} fill="var(--viz-ink-2)">
                  {d.count}
                </text>
              )}
              <text x={cx} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--viz-muted)">
                {years.length > 12 && i % 2 === 1 ? "" : d.short}
              </text>
            </g>
          );
        })}
      </svg>

      {activeYear && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 rounded border border-zinc-200 bg-white px-2 py-1 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900"
          style={{
            // 端の棒でツールチップが外にはみ出さないよう、10%〜90% に収める
            left: `${Math.min(90, Math.max(10, ((PAD.left + band * (active ?? 0) + band / 2) / W) * 100))}%`,
            top: 0,
          }}
        >
          <span className="font-semibold">{activeYear.count} 本</span>
          <span className="ml-1 text-zinc-500">{activeYear.label}</span>
        </div>
      )}
    </div>
  );
}

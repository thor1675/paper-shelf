"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { FONT, type PlacedGraph } from "@/lib/graphLayout";

const MAX_LABELS = 80;

export default function NetworkGraph({
  graph,
  param,
  unit = "本",
  hrefs,
  titles,
  action = "クリックすると一覧で絞り込み",
}: {
  graph: PlacedGraph;
  // 押したときの移動先。hrefs があればそれを使い、無ければ一覧の絞り込み（?tag= / ?author=）
  param?: "tag" | "author";
  unit?: string;
  hrefs?: Record<string, string>;
  // ツールチップに出す題名（論文の図で、円の名前が「Vaswani 2017」のように短いとき）
  titles?: Record<string, string>;
  action?: string;
}) {
  const router = useRouter();
  const [active, setActive] = useState<string | null>(null);
  const { width: W, height: H } = graph;
  const nodes = graph.nodes;
  const links = useMemo(() => {
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    return graph.links.map((l) => ({ ...l, source: byId.get(l.source)!, target: byId.get(l.target)! }));
  }, [graph]);

  const neighbors = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const l of links) {
      m.set(l.source.id, (m.get(l.source.id) ?? new Set()).add(l.target.id));
      m.set(l.target.id, (m.get(l.target.id) ?? new Set()).add(l.source.id));
    }
    return m;
  }, [links]);

  if (nodes.length === 0) return <p className="text-sm text-zinc-500">表示できるものがありません</p>;

  const labeled = new Set(
    [...nodes].sort((a, b) => b.count - a.count).slice(0, MAX_LABELS).map((n) => n.id),
  );
  const isLit = (id: string) => active === null || id === active || !!neighbors.get(active)?.has(id);
  const activeNode = nodes.find((n) => n.id === active);
  const go = (id: string) => router.push(hrefs?.[id] ?? `/?${param}=${encodeURIComponent(id)}`);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="group" aria-label="つながりの図">
        {links.map((l) => {
          const lit = active === null || l.source.id === active || l.target.id === active;
          return (
            <line
              key={`${l.source.id}\n${l.target.id}`}
              x1={l.source.x}
              y1={l.source.y}
              x2={l.target.x}
              y2={l.target.y}
              stroke={lit && active !== null ? "var(--viz-mark)" : "var(--viz-edge)"}
              strokeWidth={1 + (l.weight - 1) * 1.5}
              strokeLinecap="round"
              opacity={lit ? 0.9 : 0.15}
            />
          );
        })}
        {nodes.map((n) => (
          <g
            key={n.id}
            role="link"
            tabIndex={0}
            aria-label={`${titles?.[n.id] ?? n.id}（${n.count}${unit}）${hrefs ? "を開く" : "で絞り込む"}`}
            className="viz-focus cursor-pointer outline-none"
            opacity={isLit(n.id) ? 1 : 0.25}
            onPointerEnter={() => setActive(n.id)}
            onPointerLeave={() => setActive(null)}
            onFocus={() => setActive(n.id)}
            onBlur={() => setActive(null)}
            onClick={() => go(n.id)}
            onKeyDown={(e) => e.key === "Enter" && go(n.id)}
          >
            {/* 当たり判定は円より大きくする */}
            <circle cx={n.x} cy={n.y} r={Math.max(n.r, 12)} fill="transparent" />
            <circle
              className="viz-mark"
              cx={n.x}
              cy={n.y}
              r={n.r}
              fill="var(--viz-mark)"
              stroke="var(--background)"
              strokeWidth={2}
            />
            {(labeled.has(n.id) || n.id === active) && (
              <text
                x={n.x}
                y={n.y + n.r + 4}
                textAnchor="middle"
                dominantBaseline="hanging"
                fontSize={FONT}
                fill="var(--viz-ink-2)"
                stroke="var(--background)"
                strokeWidth={4}
                paintOrder="stroke"
              >
                {n.id}
              </text>
            )}
          </g>
        ))}
      </svg>

      {activeNode && (
        <div
          className="pointer-events-none absolute rounded border border-zinc-200 bg-white px-2 py-1 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900"
          style={{
            // ツールチップが図の外にはみ出さないよう、横は 0%〜60%、縦は 85% までに収める
            left: `${Math.min(Math.max((activeNode.x / W) * 100 - 10, 0), 60)}%`,
            top: `${Math.min(((activeNode.y + activeNode.r + FONT + 10) / H) * 100, 85)}%`,
          }}
        >
          <span className="font-semibold">
            {activeNode.count} {unit}
          </span>
          <span className="ml-1 text-zinc-500">{activeNode.id}</span>
          {titles?.[activeNode.id] && <div className="max-w-72 font-semibold">{titles[activeNode.id]}</div>}
          <div className="text-zinc-500">
            つながり {neighbors.get(activeNode.id)?.size ?? 0} 本 · {action}
          </div>
        </div>
      )}
    </div>
  );
}

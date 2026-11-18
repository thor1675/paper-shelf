"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { type CitationMap, type CitationNode, citationHref, formatCount, shortLabel } from "@/lib/api";

const W = 760;
const ROW = 26;
const TOP = 30;
const SHOWN = 20; // 片側に出す本数
const CX = W / 2;
const LEFT_X = 300;
const RIGHT_X = W - 300;
const LABEL_CHARS = 36;

// 被引用数の大きさの円（0 本で 3、10 万本で 11）
// Math.log10 はサーバ（Node.js）とブラウザで最後の桁が違うことがあり、そのままだと hydration の不一致になるので丸める
const radius = (n: number) => Math.round((3 + Math.log10(n + 1) * 1.6) * 100) / 100;
const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

// 登録済みの論文は必ず出し、残りの枠を被引用数の多い順に埋めてから、年の順に並べ直す
// （自分の論文とのつながりを見るのが一番の目的なので、被引用数が少なくても落とさない）
function pick(nodes: CitationNode[]) {
  const byCited = [...nodes].sort((a, b) => b.cited_by_count - a.cited_by_count);
  const mine = byCited.filter((n) => n.paper_id !== null);
  const others = byCited.filter((n) => n.paper_id === null);
  return [...mine, ...others]
    .slice(0, SHOWN)
    .sort((a, b) => (a.year ?? 0) - (b.year ?? 0));
}

// 左に参考文献、右にこの論文を引用している論文。円を押すとその論文を中心にした図に移る
export default function CitationMapChart({ map }: { map: CitationMap }) {
  const router = useRouter();
  const [active, setActive] = useState<CitationNode | null>(null);
  const left = pick(map.references);
  const right = pick(map.citations);
  const rows = Math.max(left.length, right.length, 1);
  const H = TOP + rows * ROW + 10;
  const cy = TOP + (rows * ROW) / 2;
  const y = (i: number, n: number) => cy - (n * ROW) / 2 + i * ROW + ROW / 2;

  function side(nodes: CitationNode[], dir: "left" | "right") {
    const x = dir === "left" ? LEFT_X : RIGHT_X;
    const mid = (x + CX) / 2;
    return nodes.map((n, i) => {
      const ny = y(i, nodes.length);
      const lit = active === null || active.work_id === n.work_id;
      const go = () => router.push(citationHref(n));
      return (
        <g
          key={n.work_id}
          role="link"
          tabIndex={0}
          aria-label={`${n.title}（${n.year ?? "年不明"}、被引用 ${n.cited_by_count} 本）を中心に見る`}
          className="viz-focus cursor-pointer outline-none"
          opacity={lit ? 1 : 0.3}
          onPointerEnter={() => setActive(n)}
          onPointerLeave={() => setActive(null)}
          onFocus={() => setActive(n)}
          onBlur={() => setActive(null)}
          onClick={go}
          onKeyDown={(e) => e.key === "Enter" && go()}
        >
          <path
            d={`M${x},${ny} C${mid},${ny} ${mid},${cy} ${CX},${cy}`}
            fill="none"
            stroke={active?.work_id === n.work_id ? "var(--viz-mark)" : "var(--viz-edge)"}
            strokeWidth={1.5}
          />
          {/* 行全体を当たり判定にする */}
          <rect
            x={dir === "left" ? 0 : x - 12}
            y={ny - ROW / 2}
            width={dir === "left" ? x + 12 : W - x + 12}
            height={ROW}
            fill="transparent"
          />
          <circle
            className="viz-mark"
            cx={x}
            cy={ny}
            r={radius(n.cited_by_count)}
            fill={n.paper_id ? "var(--viz-mark)" : "var(--viz-muted)"}
            stroke="var(--background)"
            strokeWidth={2}
          />
          <text
            x={dir === "left" ? x - 16 : x + 16}
            y={ny}
            textAnchor={dir === "left" ? "end" : "start"}
            dominantBaseline="middle"
            fontSize={11}
            fill="var(--viz-ink-2)"
          >
            <tspan fill="var(--viz-muted)">{n.year ?? "----"}</tspan>
            <tspan dx={6}>{truncate(n.title, LABEL_CHARS)}</tspan>
          </text>
        </g>
      );
    });
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
        <span>
          ← 参考文献（{left.length} / {map.references_total} 本）
        </span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <svg width="10" height="10" aria-hidden><circle cx="5" cy="5" r="5" fill="var(--viz-mark)" /></svg>
            登録済み
          </span>
          <span className="flex items-center gap-1">
            <svg width="10" height="10" aria-hidden><circle cx="5" cy="5" r="5" fill="var(--viz-muted)" /></svg>
            未登録
          </span>
          <span>円の大きさ＝被引用数</span>
        </span>
        <span>
          引用している論文（{right.length} / {map.citations_total} 本）→
        </span>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="group" aria-label="引用・被引用の図">
        {side(left, "left")}
        {side(right, "right")}
        <circle
          cx={CX}
          cy={cy}
          r={radius(map.center.cited_by_count) + 4}
          fill={map.center.paper_id ? "var(--viz-mark)" : "var(--viz-muted)"}
          stroke="var(--viz-ink)"
          strokeWidth={2}
        />
        <text x={CX} y={cy - radius(map.center.cited_by_count) - 12} textAnchor="middle" fontSize={11} fill="var(--viz-ink)">
          {shortLabel(map.center)}
        </text>
        {left.length === 0 && (
          <text x={LEFT_X} y={cy} textAnchor="end" fontSize={11} fill="var(--viz-muted)">参考文献の情報がありません</text>
        )}
        {right.length === 0 && (
          <text x={RIGHT_X} y={cy} fontSize={11} fill="var(--viz-muted)">まだ引用されていません</text>
        )}
      </svg>

      {/* 触れている論文の詳しい情報。図の外に出して、長い題名も省略せずに読めるようにする */}
      <p className="min-h-10 text-sm text-zinc-600 dark:text-zinc-400" aria-live="polite">
        {active ? (
          <>
            <span className="font-semibold text-zinc-900 dark:text-zinc-100">{active.title}</span>
            <br />
            {active.authors.slice(0, 3).join(", ")}
            {active.authors.length > 3 && ` 他${active.authors.length - 3}人`} · {active.year ?? "年不明"} · 被引用{" "}
            {formatCount(active.cited_by_count)} 本 · {active.paper_id ? "登録済み" : "未登録"} · クリックするとこの論文を中心に見る
          </>
        ) : (
          "円にカーソルを合わせると題名の全体が出ます。クリックするとその論文を中心にした図に移ります"
        )}
      </p>
    </div>
  );
}

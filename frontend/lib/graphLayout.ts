import {
  type SimulationLinkDatum,
  type SimulationNodeDatum,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";

export type Graph = {
  nodes: { id: string; count: number }[];
  edges: { source: string; target: string; weight: number }[];
};

type Node = SimulationNodeDatum & { id: string; count: number; r: number; labelW: number };
type Link = SimulationLinkDatum<Node> & { weight: number };

export const FONT = 12;
const MIN_W = 640;

// 名前の表示幅の目安（半角 0.55 文字分、全角 1 文字分）
function textWidth(s: string) {
  return [...s].reduce((w, c) => w + (c.charCodeAt(0) < 0x2e80 ? FONT * 0.55 : FONT), 0);
}

// 名前は円の真下に置くので、横幅は名前の幅の半分まで、縦は名前の下端までを占める
const halfW = (n: Node) => Math.max(n.r, n.labelW / 2);
const GAP = 24; // まとまり同士の間隔

// つながっているまとまり（連結成分）ごとに分ける。混ぜて配置すると、別のまとまりの線がまたいで見える
function components(nodes: Node[], links: Link[]) {
  const parent = new Map(nodes.map((n) => [n.id, n.id]));
  const find = (id: string): string => (parent.get(id) === id ? id : find(parent.get(id)!));
  for (const l of links) parent.set(find(l.source as string), find(l.target as string));
  const groups = new Map<string, Node[]>();
  for (const n of nodes) groups.set(find(n.id), [...(groups.get(find(n.id)) ?? []), n]);
  // 大きいまとまりから順に並べる
  return [...groups.values()].sort((a, b) => b.length - a.length || b[0].count - a[0].count);
}

// 配置を計算した結果。そのままブラウザに渡せる形（座標と線の両端の名前だけ）
export type PlacedGraph = {
  nodes: { id: string; count: number; r: number; x: number; y: number }[];
  links: { source: string; target: string; weight: number }[];
  width: number;
  height: number;
};

// d3-force で配置を計算する。サーバで 1 回だけ実行し、ブラウザには結果の座標を渡す
// （ブラウザごとに浮動小数の誤差が反復で増幅し、サーバの描画と座標がずれるのを防ぐ）
export function layout(graph: Graph): PlacedGraph {
  const nodes: Node[] = graph.nodes.map((n) => ({
    ...n,
    r: Math.min(22, 5 + Math.sqrt(n.count) * 4),
    labelW: textWidth(n.id),
  }));
  // ノードに無い名前を指す線があると d3-force が例外を投げるので、先に捨てる
  const known = new Set(nodes.map((n) => n.id));
  const edges = graph.edges.filter((e) => known.has(e.source) && known.has(e.target));
  const links: Link[] = edges.map((e) => ({ ...e }));

  // まとまりごとに配置を計算し、外接する箱を求める
  const boxes = components(nodes, links).map((group) => {
    const ids = new Set(group.map((n) => n.id));
    const own = links.filter((l) => ids.has(l.source as string));
    if (group.length > 1) {
      forceSimulation(group)
        .force("link", forceLink<Node, Link>(own).id((d) => d.id).distance(90))
        .force("charge", forceManyBody().strength(-200))
        .force("x", forceX(0).strength(0.06))
        .force("y", forceY(0).strength(0.06))
        .force("collide", forceCollide<Node>((d) => halfW(d) + 10).iterations(3))
        .stop()
        .tick(400);
    } else {
      group[0].x = 0;
      group[0].y = 0;
    }
    const left = Math.min(...group.map((n) => (n.x ?? 0) - halfW(n)));
    const right = Math.max(...group.map((n) => (n.x ?? 0) + halfW(n)));
    const top = Math.min(...group.map((n) => (n.y ?? 0) - n.r));
    const bottom = Math.max(...group.map((n) => (n.y ?? 0) + n.r + FONT + 6));
    return { group, left, top, w: right - left, h: bottom - top };
  });

  // 箱を左から右へ並べ、幅を超えたら次の段へ（本棚に詰める要領）
  const width = Math.max(MIN_W, ...boxes.map((b) => b.w + GAP * 2));
  let x = GAP;
  let y = GAP;
  let rowH = 0;
  for (const b of boxes) {
    if (x > GAP && x + b.w > width - GAP) {
      x = GAP;
      y += rowH + GAP;
      rowH = 0;
    }
    for (const n of b.group) {
      n.x = (n.x ?? 0) - b.left + x;
      n.y = (n.y ?? 0) - b.top + y;
    }
    x += b.w + GAP;
    rowH = Math.max(rowH, b.h);
  }
  const height = y + rowH + GAP;

  // 段ごとの右端の余白をそろえるため、全体を横方向の中央に寄せる
  const used = Math.max(...nodes.map((n) => (n.x ?? 0) + halfW(n)));
  const shift = (width - GAP - used) / 2;
  for (const n of nodes) n.x = (n.x ?? 0) + shift;

  return {
    nodes: nodes.map((n) => ({ id: n.id, count: n.count, r: n.r, x: round(n.x), y: round(n.y) })),
    links: edges,
    width: round(width),
    height: round(height),
  };
}

const round = (v: number | undefined) => Math.round((v ?? 0) * 10) / 10;

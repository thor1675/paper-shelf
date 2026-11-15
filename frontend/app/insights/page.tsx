import Form from "next/form";
import Link from "next/link";
import { connection } from "next/server";

import { type Paper, SERVER_API_URL, STATUSES, STATUS_LABELS } from "@/lib/api";

import { type Graph, layout } from "@/lib/graphLayout";

import NetworkGraph from "./NetworkGraph";
import YearChart from "./YearChart";

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}${path}`);
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

function Section({
  title,
  note,
  children,
  table,
}: {
  title: string;
  note: string;
  children: React.ReactNode;
  table: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2 rounded border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="text-lg font-bold">{title}</h2>
      <p className="text-sm text-zinc-500">{note}</p>
      {children}
      {/* 図を見なくても同じ数字が読めるように */}
      <details className="text-sm">
        <summary className="cursor-pointer text-zinc-500">表で見る</summary>
        <div className="mt-2 max-h-72 overflow-auto">{table}</div>
      </details>
    </section>
  );
}

function GraphTable({ graph, unit }: { graph: Graph; unit: string }) {
  const partners = (id: string) =>
    graph.edges
      .filter((e) => e.source === id || e.target === id)
      .sort((a, b) => b.weight - a.weight)
      .map((e) => `${e.source === id ? e.target : e.source}（${e.weight}）`)
      .join("、");
  return (
    <table className="w-full text-left">
      <thead className="text-zinc-500">
        <tr>
          <th className="py-1 pr-3 font-normal">名前</th>
          <th className="py-1 pr-3 text-right font-normal">{unit}数</th>
          <th className="py-1 font-normal">一緒に出てくる相手（回数）</th>
        </tr>
      </thead>
      <tbody>
        {graph.nodes.map((n) => (
          <tr key={n.id} className="border-t border-zinc-100 dark:border-zinc-800">
            <td className="py-1 pr-3">{n.id}</td>
            <td className="py-1 pr-3 text-right tabular-nums">{n.count}</td>
            <td className="py-1 text-zinc-600 dark:text-zinc-400">{partners(n.id) || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// 共著者グラフの条件。選択肢に無い値（URL の書き換えなど）は既定値に戻す
// 1 本だと論文ごとの著者が別々の塊になるだけで、つながりが読めないので選ばせない
const MIN_PAPERS = [2, 3] as const;
const MAX_AUTHORS = [5, 10, 20, 50] as const;

function pick<T extends number>(raw: string | string[] | undefined, choices: readonly T[], fallback: T): T {
  const n = Number(Array.isArray(raw) ? raw[0] : raw);
  return choices.includes(n as T) ? (n as T) : fallback;
}

export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const sp = await searchParams;
  const minPapers = pick(sp.min_papers, MIN_PAPERS, 2);
  const maxAuthors = pick(sp.max_authors, MAX_AUTHORS, 20);
  const [papers, years, tagGraph, authorGraph] = await Promise.all([
    getJson<Paper[]>("/papers"),
    getJson<{ year: number; count: number }[]>("/stats/years"),
    getJson<Graph>("/graph/tags"),
    getJson<Graph>(`/graph/authors?min_papers=${minPapers}&max_authors=${maxAuthors}`),
  ]);

  if (!papers || !years || !tagGraph || !authorGraph) {
    return (
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <p className="text-red-600">データを取得できませんでした。backend が起動しているか確認してください</p>
      </main>
    );
  }

  const statusCount = (s: string) => papers.filter((p) => p.status === s).length;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <Link href="/" className="text-sm text-zinc-500 hover:underline">
        ← 一覧へ
      </Link>
      <h1 className="text-2xl font-bold">図で見る</h1>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "論文", value: papers.length },
          ...STATUSES.map((s) => ({ label: STATUS_LABELS[s], value: statusCount(s) })),
        ].map((t) => (
          <div key={t.label} className="rounded border border-zinc-200 p-3 dark:border-zinc-800">
            <div className="text-xs text-zinc-500">{t.label}</div>
            <div className="text-2xl font-semibold">{t.value}</div>
          </div>
        ))}
      </div>

      <Section
        title="公開年ごとの本数"
        note="arXiv に初版が出た年。棒に触れると本数が出ます"
        table={
          <table className="text-left">
            <tbody>
              {years.map((y) => (
                <tr key={y.year} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="py-1 pr-6">{y.year}年</td>
                  <td className="py-1 text-right tabular-nums">{y.count} 本</td>
                </tr>
              ))}
            </tbody>
          </table>
        }
      >
        <YearChart data={years} />
      </Section>

      <Section
        title="タグのつながり"
        note={
          tagGraph.edges.length === 0
            ? "円の大きさが本数。1 本の論文に複数のタグを付けると、一緒に付いたタグ同士が線で結ばれます"
            : "円の大きさが本数、線の太さが同じ論文に一緒に付いた回数。押すとそのタグで絞り込みます"
        }
        table={<GraphTable graph={tagGraph} unit="本" />}
      >
        <NetworkGraph graph={layout(tagGraph)} param="tag" />
      </Section>

      <Section
        title="共著者のつながり"
        note={`${minPapers} 本以上に出てくる著者だけを表示（著者が ${maxAuthors} 名を超える論文は除く）。線の太さが共著の本数。押すとその著者で絞り込みます`}
        table={<GraphTable graph={authorGraph} unit="本" />}
      >
        {/* 条件を変えて「表示」を押すと URL が変わり、サーバで取り直して配置し直す */}
        <Form action="/insights" className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-1">
            <select
              name="min_papers"
              defaultValue={minPapers}
              className="rounded border border-zinc-300 bg-transparent px-1 py-0.5 dark:border-zinc-700"
            >
              {MIN_PAPERS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            本以上に出てくる著者
          </label>
          <label className="flex items-center gap-1">
            著者が
            <select
              name="max_authors"
              defaultValue={maxAuthors}
              className="rounded border border-zinc-300 bg-transparent px-1 py-0.5 dark:border-zinc-700"
            >
              {MAX_AUTHORS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            人を超える論文は除く
          </label>
          <button
            type="submit"
            className="rounded border border-zinc-300 px-2 py-0.5 dark:border-zinc-700"
          >
            表示
          </button>
        </Form>
        <NetworkGraph graph={layout(authorGraph)} param="author" />
      </Section>
    </main>
  );
}

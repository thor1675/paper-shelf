import Form from "next/form";
import Link from "next/link";
import { connection } from "next/server";

import {
  type LibraryGraph,
  type MissingItem,
  type Paper,
  type ReadStats,
  
  STATUSES,
  STATUS_LABELS,
} from "@/lib/api";

import { type Graph, layout } from "@/lib/graphLayout";

import NetworkGraph from "./NetworkGraph";
import CitationTable from "../citations/CitationTable";
import BarChart from "./BarChart";
import SyncButton from "./SyncButton";
import { unstable_rethrow } from "next/navigation";
import { serverFetch } from "@/lib/server";

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await serverFetch(`${path}`);
    return res.ok ? res.json() : null;
  } catch (e) {
    unstable_rethrow(e);
    return null;
  }
}

function fillYears(years: { year: number; count: number }[]) {
  if (years.length === 0) return [];
  const first = Math.min(...years.map((y) => y.year));
  const last = Math.max(...years.map((y) => y.year));
  return Array.from({ length: last - first + 1 }, (_, i) => ({
    label: `${first + i}年`,
    short: `'${String(first + i).slice(2)}`,
    count: years.find((y) => y.year === first + i)?.count ?? 0,
  }));
}

// 登録した論文どうしの引用を、ネットワーク図の形（名前・本数・線）にする
function libraryGraph(g: LibraryGraph): Graph {
  const label = new Map(g.nodes.map((n) => [n.paper_id, n.label]));
  const cited = new Map<number, number>();
  const pairs = new Map<string, { source: string; target: string; weight: number }>();
  for (const e of g.edges) {
    cited.set(e.target, (cited.get(e.target) ?? 0) + 1);
    const [a, b] = [label.get(e.source)!, label.get(e.target)!].sort();
    const key = `${a}\n${b}`;
    pairs.set(key, { source: a, target: b, weight: (pairs.get(key)?.weight ?? 0) + 1 });
  }
  return {
    nodes: g.nodes.map((n) => ({ id: n.label, count: cited.get(n.paper_id) ?? 0 })),
    edges: [...pairs.values()],
  };
}

// 記録の無い月も 0 本として、最初の月から今月まで並べる（日本時間）
function fillMonths(months: { month: string; count: number }[]) {
  const now = new Date(Date.now() + 9 * 3600 * 1000);
  const end = now.getUTCFullYear() * 12 + now.getUTCMonth();
  const [y, m] = months[0].month.split("-").map(Number);
  const result = [];
  for (let i = y * 12 + (m - 1); i <= end; i++) {
    const label = `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`;
    result.push({ label, short: `${(i % 12) + 1}月`, count: months.find((x) => x.month === label)?.count ?? 0 });
  }
  return result;
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
      {table && (
        <details className="text-sm">
          <summary className="cursor-pointer text-zinc-500">表で見る</summary>
          <div className="mt-2 max-h-72 overflow-auto">{table}</div>
        </details>
      )}
    </section>
  );
}

function GraphTable({ graph, countLabel }: { graph: Graph; countLabel: string }) {
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
          <th className="py-1 pr-3 text-right font-normal">{countLabel}</th>
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
  const [papers, years, tagGraph, authorGraph, library, missing, reading] = await Promise.all([
    getJson<Paper[]>("/papers"),
    getJson<{ year: number; count: number }[]>("/stats/years"),
    getJson<Graph>("/graph/tags"),
    getJson<Graph>(`/graph/authors?min_papers=${minPapers}&max_authors=${maxAuthors}`),
    getJson<LibraryGraph>("/citations/library"),
    // OpenAlex への問い合わせを含むので、失敗しても他の図は出す
    getJson<MissingItem[]>("/citations/missing?limit=20"),
    getJson<ReadStats>("/stats/read"),
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
      <h1 className="text-2xl font-bold">図解</h1>

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
        note="arXiv に初版が出た年。棒にカーソルを合わせると本数が出ます"
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
        <BarChart
          // 論文の無い年も 0 本として並べる（年が飛ぶと間隔が嘘になる）
          data={fillYears(years)}
          ariaLabel="公開年ごとの論文数"
        />
      </Section>

      <Section
        title="タグのつながり"
        note={
          tagGraph.edges.length === 0
            ? "円の大きさが本数。1 本の論文に複数のタグを付けると、一緒に付いたタグ同士が線で結ばれます"
            : "円の大きさが本数、線の太さが同じ論文に一緒に付いた回数。クリックするとそのタグで絞り込みます"
        }
        table={<GraphTable graph={tagGraph} countLabel="本数" />}
      >
        <NetworkGraph graph={layout(tagGraph)} param="tag" />
      </Section>

      <Section
        title="共著者のつながり"
        note={`${minPapers} 本以上に出てくる著者だけを表示（著者が ${maxAuthors} 名を超える論文は除く）。線の太さが共著の本数。クリックするとその著者で絞り込みます`}
        table={<GraphTable graph={authorGraph} countLabel="本数" />}
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

      <Section
        title="登録した論文どうしの引用"
        note="線は引用の関係。円の大きさは、登録した論文の何本に引用されているか。クリックするとその論文の詳細を開きます"
        table={
          library && (
            <GraphTable graph={libraryGraph(library)} countLabel="引用された本数" />
          )
        }
      >
        <SyncButton />
        {library === null ? (
          <p className="text-sm text-red-600">引用の情報を取得できませんでした</p>
        ) : library.nodes.length === 0 ? (
          <p className="text-sm text-zinc-500">
            まだ引用の関係が見つかっていません。「引用の情報を更新」をクリックすると OpenAlex から取得します
          </p>
        ) : (
          <NetworkGraph
            graph={layout(libraryGraph(library))}
            unit="本に引用"
            hrefs={Object.fromEntries(library.nodes.map((n) => [n.label, `/papers/${n.paper_id}`]))}
            titles={Object.fromEntries(library.nodes.map((n) => [n.label, n.title]))}
            action="クリックすると詳細を開く"
          />
        )}
        {library && library.unsynced > 0 && (
          <p className="text-xs text-zinc-500">まだ同期していない論文が {library.unsynced} 本あります</p>
        )}
      </Section>

      <Section
        title="よく引用されているのに未登録の論文"
        note="登録した論文が参考文献によく挙げている論文。arXiv にあるものはここから登録できます"
        table={null}
      >
        {missing === null ? (
          <p className="text-sm text-red-600">引用の情報を取得できませんでした。しばらくしてからもう一度試してください</p>
        ) : (
          <CitationTable
            nodes={missing}
            extra={(n) => `登録した ${(n as MissingItem).cited_by_papers.length} 本が引用`}
          />
        )}
      </Section>

      <Section
        title="月ごとに読了した本数"
        note="ステータスを「読了」にした月で数えます。読了以外に戻すと数えなくなります"
        table={
          reading && (
            <table className="text-left">
              <tbody>
                {reading.months.map((m) => (
                  <tr key={m.month} className="border-t border-zinc-100 dark:border-zinc-800">
                    <td className="py-1 pr-6">{m.month}</td>
                    <td className="py-1 text-right tabular-nums">{m.count} 本</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      >
        {reading === null ? (
          <p className="text-sm text-red-600">読書の記録を取得できませんでした</p>
        ) : reading.months.length === 0 ? (
          <p className="text-sm text-zinc-500">まだ記録がありません。論文のステータスを「読了」にすると数えます</p>
        ) : (
          <BarChart data={fillMonths(reading.months)} ariaLabel="月ごとに読了した本数" />
        )}
        {reading && reading.unknown > 0 && (
          <p className="text-xs text-zinc-500">
            記録を始める前に「読了」にした {reading.unknown} 本は、月が分からないので数えていません
          </p>
        )}
      </Section>
    </main>
  );
}

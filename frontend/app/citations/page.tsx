import Form from "next/form";
import Link from "next/link";
import { connection } from "next/server";

import { type CitationMap, formatCount } from "@/lib/api";

import RegisterButton from "../RegisterButton";
import CitationMapChart from "./CitationMapChart";
import CitationTable from "./CitationTable";
import { unstable_rethrow } from "next/navigation";
import { serverFetch } from "@/lib/server";

export default async function CitationsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const sp = await searchParams;
  const key = (Array.isArray(sp.key) ? sp.key[0] : sp.key)?.trim() ?? "";

  let map: CitationMap | null = null;
  let error: string | null = null;
  if (key) {
    try {
      const res = await serverFetch(`/citations/map?key=${encodeURIComponent(key)}`);
      const body = await res.json();
      if (res.ok) map = body;
      else error = typeof body.detail === "string" ? body.detail : `エラーが発生しました（${res.status}）`;
    } catch (e) {
    unstable_rethrow(e);
      error = "backend に接続できませんでした";
    }
  }
  const c = map?.center;

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-bold">引用図</h1>

      <Form action="/citations" className="flex gap-2">
        <input
          key={key}
          name="key"
          defaultValue={key}
          aria-label="中心にする論文の arXiv ID か URL"
          placeholder="arXiv ID か URL（例: 1706.03762）"
          className="flex-1 rounded border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
        />
        <button type="submit" className="rounded bg-zinc-900 px-4 py-2 text-white dark:bg-zinc-100 dark:text-zinc-900">
          表示
        </button>
      </Form>

      {!key && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          登録していない論文でも表示可能です。引用の情報は OpenAlex から取得します（一度取得したものは 7 日間保存されます）
        </p>
      )}
      {error && <p className="text-red-600">{error}</p>}

      {map && c && (
        <>
          <header className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-xl font-bold break-words">{c.title}</h2>
              <p className="text-sm break-words text-zinc-600 dark:text-zinc-400">
                {c.authors.slice(0, 5).join(", ")}
                {c.authors.length > 5 && ` 他${c.authors.length - 5}人`} · {c.year ?? "年不明"} · 被引用{" "}
                {formatCount(c.cited_by_count)} 本
                {c.paper_id && (
                  <>
                    {" · "}
                    <Link href={`/papers/${c.paper_id}`} className="underline">
                      詳細
                    </Link>
                  </>
                )}
              </p>
            </div>
            {c.arxiv_id && <RegisterButton arxivId={c.arxiv_id} paperId={c.paper_id} />}
          </header>

          <CitationMapChart map={map} />

          <div className="grid gap-6 md:grid-cols-2">
            <section className="flex flex-col gap-2">
              <h2 className="text-lg font-bold">参考文献（{map.references_total} 本）</h2>
              <p className="text-xs text-zinc-500">被引用数の多い順</p>
              <CitationTable nodes={map.references} empty="参考文献はありません" />
            </section>
            <section className="flex flex-col gap-2">
              <h2 className="text-lg font-bold">引用している論文（{map.citations_total} 本）</h2>
              <p className="text-xs text-zinc-500">
                被引用数の多い {map.citations.length} 本{map.citations_total > map.citations.length && "（全部は OpenAlex で見られます）"}
              </p>
              <CitationTable nodes={map.citations} empty="引用している論文はありません" />
              {map.citations_total > map.citations.length && (
                <a
                  href={`https://openalex.org/works?filter=cites:${c.work_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm underline"
                >
                  OpenAlex で全部見る
                </a>
              )}
            </section>
          </div>
        </>
      )}
    </main>
  );
}

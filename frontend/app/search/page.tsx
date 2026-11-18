import Form from "next/form";
import Link from "next/link";
import { connection } from "next/server";

import { type SearchItem } from "@/lib/api";

import SearchResultList from "../SearchResultList";
import { unstable_rethrow } from "next/navigation";
import { serverFetch } from "@/lib/server";

type Result = { total: number; start: number; items: SearchItem[] };
const PAGE = 20;

function first(v: string | string[] | undefined) {
  return (Array.isArray(v) ? v[0] : v)?.trim() ?? "";
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const sp = await searchParams;
  const q = first(sp.q);
  const sort = first(sp.sort) === "newest" ? "newest" : "relevance";
  const start = Math.max(0, Math.floor(Number(first(sp.start)) || 0));

  let result: Result | null = null;
  let error: string | null = null;
  if (q) {
    const params = new URLSearchParams({ q, sort, start: String(start) });
    try {
      const res = await serverFetch(`/arxiv/search?${params}`);
      const body = await res.json();
      if (res.ok) result = body;
      else error = typeof body.detail === "string" ? body.detail : `エラーが発生しました（${res.status}）`;
    } catch (e) {
    unstable_rethrow(e);
      error = "backend に接続できませんでした";
    }
  }

  const pageHref = (s: number) => `/search?${new URLSearchParams({ q, sort, start: String(s) })}`;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-bold">arXiv 検索</h1>

      <Form action="/search" className="flex flex-col gap-2">
        <div className="flex gap-2">
          <input
            key={q}
            name="q"
            defaultValue={q}
            aria-label="arXiv を検索するキーワード"
            placeholder="例: instruction following retrieval"
            className="flex-1 rounded border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
          />
          <select
            name="sort"
            defaultValue={sort}
            aria-label="並び順"
            className="rounded border border-zinc-300 bg-transparent px-2 dark:border-zinc-700"
          >
            <option value="relevance">関連度順</option>
            <option value="newest">新しい順</option>
          </select>
          <button
            type="submit"
            className="rounded bg-zinc-900 px-4 py-2 text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            検索
          </button>
        </div>
        <p className="text-xs text-zinc-500">
          スペースで区切るとすべての語を含む論文を探します（AND 検索）。&quot;query rewriting&quot; のように &quot; で囲むと語句のまま探します。ti:（タイトル）や au:（著者）で探す項目を指定できます
        </p>
      </Form>

      {error && <p className="text-red-600">{error}</p>}

      {result && (
        <>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {result.total} 本中 {result.items.length ? `${start + 1}〜${start + result.items.length}` : "0"} 本目
          </p>
          {result.items.length === 0 ? (
            <p className="text-zinc-500">見つかりませんでした</p>
          ) : (
            <SearchResultList items={result.items} />
          )}
          <div className="flex justify-between text-sm">
            {start > 0 ? (
              <Link href={pageHref(Math.max(0, start - PAGE))} className="underline">
                ← 前の {PAGE} 本
              </Link>
            ) : (
              <span />
            )}
            {start + PAGE < result.total && (
              <Link href={pageHref(start + PAGE)} className="underline">
                次の {PAGE} 本 →
              </Link>
            )}
          </div>
        </>
      )}
    </main>
  );
}

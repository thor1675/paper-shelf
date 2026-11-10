import Link from "next/link";
import { connection } from "next/server";

import { type Paper, SERVER_API_URL, type TagCount } from "@/lib/api";
import { type Filters, hasFilters, parseFilters, toQuery, toggleTag } from "@/lib/filters";

import AddPaperForm from "./AddPaperForm";
import FilterBar from "./FilterBar";
import StatusSelect from "./StatusSelect";

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}${path}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function formatAuthors(authors: string[]) {
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")} 他${authors.length - 3}名`;
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  // ビルド時ではなく、リクエストのたびに一覧を取得する
  await connection();
  const filters: Filters = parseFilters(await searchParams);
  // URL のクエリをそのまま backend の GET /papers に渡す（名前をそろえてある）
  const [papers, tags] = await Promise.all([
    getJson<Paper[]>(`/papers${toQuery(filters)}`),
    getJson<TagCount[]>("/tags"),
  ]);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-bold">paper-shelf</h1>

      <AddPaperForm />

      {papers !== null && (
        <FilterBar filters={filters} tags={tags ?? []} count={papers.length} />
      )}

      {papers === null ? (
        <p className="text-red-600">一覧を取得できませんでした。backend が起動しているか確認してください。</p>
      ) : papers.length === 0 ? (
        <p className="text-zinc-500">
          {hasFilters(filters)
            ? "条件に合う論文がありません。"
            : "まだ論文がありません。上のフォームから登録してください。"}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {papers.map((p) => (
            <li
              key={p.id}
              className="rounded border border-zinc-200 p-4 dark:border-zinc-800"
            >
              <div className="flex items-start justify-between gap-3">
                <Link href={`/papers/${p.id}`} className="font-semibold hover:underline">
                  {p.title}
                </Link>
                <StatusSelect paperId={p.id} status={p.status} />
              </div>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {formatAuthors(p.authors)} · {p.published} · arXiv:{p.arxiv_id}
              </p>
              {p.tags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {p.tags.map((t) => (
                    <Link
                      key={t}
                      href={toggleTag(filters, t)}
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        filters.tags.includes(t)
                          ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                          : "bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700"
                      }`}
                    >
                      {t}
                    </Link>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

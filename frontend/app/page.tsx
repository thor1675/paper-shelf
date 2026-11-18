import { connection } from "next/server";

import { type Paper, type TagCount } from "@/lib/api";
import { type Filters, hasFilters, parseFilters, toQuery } from "@/lib/filters";

import AddPaperForm from "./AddPaperForm";
import BulkAddForm from "./BulkAddForm";
import FilterBar from "./FilterBar";
import PaperList from "./PaperList";
import { unstable_rethrow } from "next/navigation";
import { serverFetch } from "@/lib/server";

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await serverFetch(`${path}`);
    if (!res.ok) return null;
    return res.json();
  } catch (e) {
    unstable_rethrow(e);
    return null;
  }
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
    <main className="flex mx-auto w-full max-w-(--page-max) flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-bold">論文一覧</h1>

      <AddPaperForm />
      <BulkAddForm />

      {papers !== null && (
        <FilterBar filters={filters} tags={tags ?? []} count={papers.length} />
      )}

      {papers === null ? (
        <p className="text-red-600">一覧を取得できませんでした。backend が起動しているか確認してください</p>
      ) : papers.length === 0 ? (
        <p className="text-zinc-500">
          {hasFilters(filters)
            ? "条件に合う論文がありません"
            : "まだ論文がありません。上のフォームから登録してください"}
        </p>
      ) : (
        <PaperList papers={papers} filters={filters} allTags={(tags ?? []).map((t) => t.name)} />
      )}
    </main>
  );
}

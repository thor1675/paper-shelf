import Link from "next/link";
import { notFound } from "next/navigation";

import { type Paper } from "@/lib/api";

import Reader, { type Status } from "./Reader";
import { serverFetch } from "@/lib/server";

export default async function ReadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await serverFetch(`/papers/${encodeURIComponent(id)}`);
  if (res.status === 404 || res.status === 422) notFound();
  if (!res.ok) throw new Error(`論文を取得できませんでした（${res.status}）`);
  const paper: Paper = await res.json();
  // 翻訳の状態。取れなくても画面は出し、Reader の中でもう一度取れるようにする
  const initial: Status | null = await serverFetch(`/papers/${paper.id}/translation`)
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);

  return (
    <main className="flex mx-auto w-full max-w-(--page-max-lg) flex-col gap-4 px-4 py-10">
      <Link href={`/papers/${paper.id}`} className="text-sm text-zinc-500 hover:underline">
        ← 詳細へ
      </Link>
      <h1 className="text-2xl font-bold break-words">{paper.title}</h1>
      <Reader paperId={paper.id} arxivUrl={paper.arxiv_url} initial={initial} />
    </main>
  );
}

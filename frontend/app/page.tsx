import Link from "next/link";
import { connection } from "next/server";

import { type Paper, SERVER_API_URL } from "@/lib/api";

import AddPaperForm from "./AddPaperForm";
import StatusSelect from "./StatusSelect";

async function getPapers(): Promise<Paper[] | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/papers`);
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

export default async function Home() {
  // ビルド時ではなく、リクエストのたびに一覧を取得する
  await connection();
  const papers = await getPapers();

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-bold">paper-shelf</h1>

      <AddPaperForm />

      {papers === null ? (
        <p className="text-red-600">一覧を取得できませんでした。backend が起動しているか確認してください。</p>
      ) : papers.length === 0 ? (
        <p className="text-zinc-500">まだ論文がありません。上のフォームから登録してください。</p>
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
                    <span
                      key={t}
                      className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800"
                    >
                      {t}
                    </span>
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

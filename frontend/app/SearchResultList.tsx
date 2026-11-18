import Link from "next/link";

import { type SearchItem, formatAuthors } from "@/lib/api";

import RegisterButton from "./RegisterButton";

// arXiv の検索結果と新着で共通の一覧
export default function SearchResultList({ items }: { items: SearchItem[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {items.map((p) => (
        <li key={p.arxiv_id} className="rounded border border-zinc-200 p-4 dark:border-zinc-800">
          <div className="flex items-start justify-between gap-3">
            <a
              href={p.arxiv_url}
              target="_blank"
              rel="noopener noreferrer"
              className="min-w-0 font-semibold break-words hover:underline"
            >
              {p.title}
            </a>
            <RegisterButton arxivId={p.arxiv_id} paperId={p.paper_id} />
          </div>
          <p className="mt-1 text-sm break-words text-zinc-600 dark:text-zinc-400">
            {formatAuthors(p.authors)} · {p.published} · arXiv:{p.arxiv_id} ·{" "}
            <Link href={`/citations?key=${encodeURIComponent(p.arxiv_id)}`} className="underline">
              引用関係を確認
            </Link>
          </p>
          <details className="mt-1 text-sm">
            <summary className="cursor-pointer text-zinc-500">abstract</summary>
            <p className="mt-1 leading-6 text-zinc-700 dark:text-zinc-300">{p.abstract}</p>
          </details>
        </li>
      ))}
    </ul>
  );
}

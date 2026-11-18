import Link from "next/link";

import { type CitationNode, citationHref, formatCount, shortLabel } from "@/lib/api";

import RegisterButton from "../RegisterButton";

// 引用の図の全件。arXiv にある未登録の論文はここから登録できる
export default function CitationTable({
  nodes,
  extra,
  empty = "ありません",
}: {
  nodes: CitationNode[];
  // 行ごとに足す説明（「登録した 20 本が引用」など）
  extra?: (n: CitationNode) => React.ReactNode;
  // 0 本のときの文
  empty?: string;
}) {
  if (nodes.length === 0) return <p className="text-sm text-zinc-500">{empty}</p>;
  return (
    <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
      {nodes.map((n) => (
        <li key={n.work_id} className="flex items-start justify-between gap-3 py-2">
          <div className="min-w-0">
            <Link href={citationHref(n)} className="text-sm font-semibold break-words hover:underline">
              {n.title}
            </Link>
            <p className="text-xs text-zinc-500">
              {shortLabel(n)} · 被引用 {formatCount(n.cited_by_count)} 本
              {extra && <> · {extra(n)}</>}
            </p>
          </div>
          {n.arxiv_id ? (
            <RegisterButton arxivId={n.arxiv_id} paperId={n.paper_id} />
          ) : n.paper_id ? (
            <Link href={`/papers/${n.paper_id}`} className="shrink-0 text-sm text-zinc-500 underline">
              登録済み
            </Link>
          ) : (
            <a
              href={`https://openalex.org/${n.work_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 text-xs text-zinc-500 underline"
              title="arXiv に無い論文は登録できない"
            >
              arXiv なし
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

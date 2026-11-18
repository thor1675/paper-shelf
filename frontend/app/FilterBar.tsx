import Form from "next/form";
import Link from "next/link";

import { BROWSER_API_URL, STATUSES, STATUS_LABELS, type TagCount } from "@/lib/api";
import { type Filters, filterHref, hasFilters, toQuery, toggleTag } from "@/lib/filters";

// 並べる項目と向きは別々に選ぶ（項目を変えても向きはそのまま）
const SORTS: { label: string; sort: Filters["sort"] }[] = [
  { label: "追加順", sort: "created_at" },
  { label: "公開順", sort: "published" },
  { label: "被引用数順", sort: "citations" },
];
const ORDERS: { label: string; order: Filters["order"] }[] = [
  { label: "降順", order: "desc" },
  { label: "昇順", order: "asc" },
];

function chip(active: boolean) {
  return `rounded-full px-2.5 py-0.5 text-sm ${
    active
      ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
      : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
  }`;
}

// JavaScript を使わない絞り込み。リンクを押すかフォームを送ると URL のクエリが変わり、
// Server Component の一覧がその条件で取り直される
export default function FilterBar({
  filters,
  tags,
  count,
}: {
  filters: Filters;
  tags: TagCount[];
  count: number;
}) {
  // URL で指定されているが /tags に無いタグ（打ち間違いなど）も、外せるように表示する
  const tagNames = [
    ...tags.map((t) => t.name),
    ...filters.tags.filter((t) => !tags.some((x) => x.name === t)),
  ];
  const countOf = (name: string) => tags.find((t) => t.name === name)?.count ?? 0;

  return (
    <section className="flex flex-col gap-3">
      {/* 検索してもタグ・ステータス・並び順は保つため、hidden で一緒に送る */}
      <Form action="/" className="flex gap-2">
        <input
          // key: 条件をクリアしたり別の条件のリンクで移動したとき、前の検索語を残さない
          key={filters.q ?? ""}
          name="q"
          aria-label="タイトル・abstract を検索"
          defaultValue={filters.q}
          placeholder="タイトル・abstract を検索"
          className="flex-1 rounded border border-zinc-300 bg-transparent px-3 py-1.5 text-sm dark:border-zinc-700"
        />
        {filters.tags.map((t) => (
          <input key={t} type="hidden" name="tag" value={t} />
        ))}
        {filters.status && <input type="hidden" name="status" value={filters.status} />}
        {filters.author && <input type="hidden" name="author" value={filters.author} />}
        {filters.sort !== "created_at" && <input type="hidden" name="sort" value={filters.sort} />}
        {filters.order !== "desc" && <input type="hidden" name="order" value={filters.order} />}
        <button
          type="submit"
          className="rounded border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700"
        >
          検索
        </button>
      </Form>

      <div className="flex flex-wrap items-center gap-1">
        <span className="mr-1 w-16 text-xs text-zinc-500">ステータス</span>
        <Link href={filterHref(filters, { status: undefined })} className={chip(!filters.status)}>
          すべて
        </Link>
        {STATUSES.map((s) => (
          <Link key={s} href={filterHref(filters, { status: s })} className={chip(filters.status === s)}>
            {STATUS_LABELS[s]}
          </Link>
        ))}
      </div>

      {tagNames.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="mr-1 w-16 text-xs text-zinc-500">タグ</span>
          {tagNames.map((t) => (
            <Link key={t} href={toggleTag(filters, t)} className={chip(filters.tags.includes(t))}>
              {t}
              <span className="ml-1 text-xs opacity-60">{countOf(t)}</span>
            </Link>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1">
        <span className="mr-1 w-16 text-xs text-zinc-500">並び順</span>
        {SORTS.map((s) => (
          <Link key={s.sort} href={filterHref(filters, { sort: s.sort })} className={chip(filters.sort === s.sort)}>
            {s.label}
          </Link>
        ))}
        <span className="mx-1 text-zinc-300 dark:text-zinc-700" aria-hidden>
          |
        </span>
        {ORDERS.map((o) => (
          <Link key={o.order} href={filterHref(filters, { order: o.order })} className={chip(filters.order === o.order)}>
            {o.label}
          </Link>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
        <span>{count} 件</span>
        {/* 今の絞り込み条件のまま .bib をダウンロードする（ブラウザが backend から直接受け取る） */}
        {count > 0 && (
          <a href={`${BROWSER_API_URL}/papers/export.bib${toQuery(filters)}`} download className="underline">
            BibTeX で書き出す
          </a>
        )}
        {filters.author && (
          <Link
            href={filterHref(filters, { author: undefined })}
            className="rounded-full bg-zinc-100 px-2.5 py-0.5 dark:bg-zinc-800"
          >
            著者: {filters.author} ×
          </Link>
        )}
        {hasFilters(filters) && (
          <Link href={filterHref(filters, { tags: [], status: undefined, author: undefined, q: undefined })} className="underline">
            条件をクリア
          </Link>
        )}
      </div>
    </section>
  );
}

import { STATUSES, type Status, addTag } from "./api";

// 一覧の絞り込み条件。URL のクエリ（/?tag=nlp&status=read&q=bert）と相互に変換する
export type Filters = {
  tags: string[];
  status?: Status;
  author?: string;
  q?: string;
  sort: "created_at" | "published";
  order: "asc" | "desc";
};

type SearchParams = { [key: string]: string | string[] | undefined };

function first(v: string | string[] | undefined): string | undefined {
  const s = Array.isArray(v) ? v[0] : v;
  return s?.trim() || undefined;
}

// 不正な値は無視する（backend に渡すと 422 になるため）
export function parseFilters(sp: SearchParams): Filters {
  const tag = sp.tag;
  const status = first(sp.status);
  const sort = first(sp.sort);
  const order = first(sp.order);
  return {
    // 保存時と同じく小文字にそろえる（?tag=NLP でも nlp のチップが選択状態になる）
    tags: (Array.isArray(tag) ? tag : tag ? [tag] : []).reduce(addTag, [] as string[]),
    status: STATUSES.includes(status as Status) ? (status as Status) : undefined,
    author: first(sp.author),
    q: first(sp.q),
    sort: sort === "published" ? "published" : "created_at",
    order: order === "asc" ? "asc" : "desc",
  };
}

export function toQuery(f: Filters): string {
  const p = new URLSearchParams();
  f.tags.forEach((t) => p.append("tag", t));
  if (f.status) p.set("status", f.status);
  if (f.author) p.set("author", f.author);
  if (f.q) p.set("q", f.q);
  // 既定値（追加が新しい順）は URL に出さない
  if (f.sort !== "created_at") p.set("sort", f.sort);
  if (f.order !== "desc") p.set("order", f.order);
  const s = p.toString();
  return s ? `?${s}` : "";
}

// 今の条件の一部だけを変えた一覧の URL
export function filterHref(f: Filters, changes: Partial<Filters>): string {
  return `/${toQuery({ ...f, ...changes })}`;
}

export function toggleTag(f: Filters, tag: string): string {
  const tags = f.tags.includes(tag) ? f.tags.filter((t) => t !== tag) : [...f.tags, tag];
  return filterHref(f, { tags });
}

export function hasFilters(f: Filters): boolean {
  return f.tags.length > 0 || !!f.status || !!f.author || !!f.q;
}

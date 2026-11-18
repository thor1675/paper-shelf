"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  BROWSER_API_URL, apiFetch,
  type Paper,
  STATUSES,
  STATUS_LABELS,
  type Status,
  addTag,
  errorMessage,
  formatAuthors,
  formatCount,
} from "@/lib/api";
import { useConfirm } from "@/components/useConfirm";
import { type Filters, toggleTag } from "@/lib/filters";

import StatusSelect from "./StatusSelect";

// 論文の一覧。チェックを付けた論文に、まとめてタグを付け外しする・状態を変える・削除する
export default function PaperList({ papers, filters, allTags }: { papers: Paper[]; filters: Filters; allTags: string[] }) {
  const { confirm: ask, dialog } = useConfirm();
  const router = useRouter();
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [tagInput, setTagInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  // 絞り込みを変えて一覧から消えた論文は、選択からも外す
  const selected = papers.filter((p) => checked.has(p.id));
  const selectedTags = [...new Set(selected.flatMap((p) => p.tags))].sort();
  const allChecked = papers.length > 0 && selected.length === papers.length;

  function toggle(id: number) {
    const next = new Set(checked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setChecked(next);
  }

  async function apply(body: Record<string, unknown>, done: string) {
    setBusy(true);
    setMessage(null);
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/papers/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: selected.map((p) => p.id), ...body }),
      });
      if (!res.ok) {
        setMessage(await errorMessage(res));
        return false;
      }
      setMessage(done);
      startTransition(() => router.refresh());
      return true;
    } catch {
      setMessage("backend に接続できませんでした");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function addTags(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const tags = tagInput.split(/[,、]/).reduce(addTag, [] as string[]);
    if (tags.length === 0) return;
    if (await apply({ add_tags: tags }, `${selected.length} 件に「${tags.join("」「")}」を付けました`)) setTagInput("");
  }

  async function remove() {
    if (!(await ask({ title: `選んだ ${selected.length} 件を削除しますか？`, description: "元に戻せません", action: "削除", destructive: true }))) return;
    if (await apply({ delete: true }, `${selected.length} 件を削除しました`)) setChecked(new Set());
  }

  return (
    <div className="flex flex-col gap-3">
      {dialog}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={allChecked}
            onChange={() => setChecked(allChecked ? new Set() : new Set(papers.map((p) => p.id)))}
          />
          すべて選ぶ
        </label>
        {selected.length > 0 && <span className="text-zinc-500">{selected.length} 件を選択中</span>}
      </div>

      {selected.length > 0 && (
        // 選んでいる間は、まとめて操作する欄を画面の上に貼り付けておく
        <div className="sticky top-0 z-10 flex flex-col gap-2 rounded border border-zinc-300 bg-white p-3 text-sm shadow-sm dark:border-zinc-700 dark:bg-zinc-950">
          <div className="flex flex-wrap items-center gap-2">
            <form onSubmit={addTags} className="flex items-center gap-1">
              <input
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                list="bulk-tags"
                placeholder="付けるタグ（カンマ区切り）"
                aria-label="選んだ論文に付けるタグ"
                className="w-48 rounded border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
              />
              <datalist id="bulk-tags">
                {allTags.map((t) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
              <button type="submit" disabled={busy} className="rounded border border-zinc-300 px-2 py-1 disabled:opacity-50 dark:border-zinc-700">
                付ける
              </button>
            </form>

            {selectedTags.length > 0 && (
              <select
                value=""
                disabled={busy}
                aria-label="選んだ論文から外すタグ"
                onChange={(e) => e.target.value && apply({ remove_tags: [e.target.value] }, `${selected.length} 件から「${e.target.value}」を外しました`)}
                className="rounded border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
              >
                <option value="">タグを外す…</option>
                {selectedTags.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            )}

            <select
              value=""
              disabled={busy}
              aria-label="選んだ論文のステータス"
              onChange={(e) =>
                e.target.value &&
                apply({ status: e.target.value }, `${selected.length} 件を「${STATUS_LABELS[e.target.value as Status]}」にしました`)
              }
              className="rounded border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
            >
              <option value="">ステータス変更</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </select>

            <button type="button" onClick={remove} disabled={busy} className="ml-auto text-red-600 hover:underline disabled:opacity-50">
              削除
            </button>
          </div>
          {message && <p className="text-zinc-600 dark:text-zinc-400">{message}</p>}
        </div>
      )}

      <ul className="flex flex-col gap-3">
        {papers.map((p) => (
          <li
            key={p.id}
            className={`flex gap-3 rounded border p-4 ${
              checked.has(p.id) ? "border-zinc-500 dark:border-zinc-400" : "border-zinc-200 dark:border-zinc-800"
            }`}
          >
            <input
              type="checkbox"
              checked={checked.has(p.id)}
              onChange={() => toggle(p.id)}
              aria-label={`「${p.title}」を選ぶ`}
              className="mt-1 shrink-0"
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3">
                <Link href={`/papers/${p.id}`} className="min-w-0 font-semibold break-words hover:underline">
                  {p.title}
                </Link>
                <StatusSelect paperId={p.id} title={p.title} status={p.status} />
              </div>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {formatAuthors(p.authors)} · {p.published} · arXiv:{p.arxiv_id}
                {p.citation_count !== null && ` · 被引用 ${formatCount(p.citation_count)} 本`}
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
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

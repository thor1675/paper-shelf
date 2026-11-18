"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { BROWSER_API_URL, apiFetch, errorMessage } from "@/lib/api";

// タグ 1 つ分。名前を変える（既にある名前にすると 1 つにまとまる）・全部の論文から外す
export default function TagRow({ name, count, others }: { name: string; count: number; others: string[] }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const target = value.trim().toLowerCase();
  const merging = target !== name && others.includes(target);

  async function call(url: string, init: RequestInit) {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(url, init);
      if (!res.ok) {
        setError(await errorMessage(res));
        return false;
      }
      router.refresh();
      return true;
    } catch {
      setError("backend に接続できませんでした");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function rename(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!target || target === name) return setEditing(false);
    if (merging && !confirm(`「${name}」を「${target}」にまとめますか？（${count} 本の論文が対象）`)) return;
    if (
      await call(`${BROWSER_API_URL}/tags/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old: name, new: target }),
      })
    )
      setEditing(false);
  }

  async function remove() {
    if (!confirm(`「${name}」を ${count} 本の論文から外しますか？（論文は消えません）`)) return;
    await call(`${BROWSER_API_URL}/tags/${encodeURIComponent(name)}`, { method: "DELETE" });
  }

  return (
    <li className="flex flex-col gap-1 px-4 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {editing ? (
          <form onSubmit={rename} className="flex flex-1 flex-wrap items-center gap-2">
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              list="tag-names"
              autoFocus
              aria-label={`「${name}」の新しい名前`}
              className="min-w-40 flex-1 rounded border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700"
            />
            <button type="submit" disabled={busy} className="rounded bg-zinc-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900">
              {merging ? "まとめる" : "変更"}
            </button>
            <button type="button" onClick={() => (setEditing(false), setValue(name))} className="text-sm text-zinc-500">
              キャンセル
            </button>
          </form>
        ) : (
          <>
            <Link href={`/?tag=${encodeURIComponent(name)}`} className="min-w-0 break-words hover:underline">
              {name}
              <span className="ml-2 text-xs text-zinc-500">{count} 件</span>
            </Link>
            <div className="flex gap-3 text-sm">
              <button type="button" onClick={() => setEditing(true)} className="text-zinc-500 hover:underline">
                名前を変える
              </button>
              <button type="button" onClick={remove} disabled={busy} className="text-zinc-500 hover:text-red-600 disabled:opacity-50">
                外す
              </button>
            </div>
          </>
        )}
      </div>
      {merging && editing && <p className="text-xs text-zinc-500">「{target}」は既にあるので、2 つのタグが 1 つにまとまります</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </li>
  );
}

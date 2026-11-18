"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useConfirm } from "@/components/useConfirm";
import { BROWSER_API_URL, apiFetch, errorMessage } from "@/lib/api";

// キーワードの追加
export function AddWatchForm() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/watches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      setQuery("");
      router.refresh();
    } catch {
      setError("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="新着を知らせるキーワード"
          placeholder="例: instruction following retrieval"
          className="flex-1 rounded border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          追加
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
}

// キーワードの削除
export function DeleteWatchButton({ id, query }: { id: number; query: string }) {
  const { confirm: ask, dialog } = useConfirm();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function remove() {
    if (!(await ask({ title: `「${query}」の通知をやめますか？`, action: "やめる", destructive: true }))) return;
    setBusy(true);
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/watches/${id}`, { method: "DELETE" });
      if (!res.ok) alert(await errorMessage(res));
      router.refresh();
    } catch {
      alert("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
    {dialog}
    <button
      type="button"
      onClick={remove}
      disabled={busy}
      aria-label={`「${query}」を削除`}
      className="text-sm text-zinc-500 hover:text-red-600 disabled:opacity-50"
    >
      削除
    </button>
    </>
  );
}

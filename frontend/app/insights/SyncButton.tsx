"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { BROWSER_API_URL, apiFetch, errorMessage } from "@/lib/api";

// 被引用数と参考文献を OpenAlex から取り直す。同期から 7 日たっていない論文は問い合わせない
export default function SyncButton({ force = false }: { force?: boolean }) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [, startTransition] = useTransition();

  async function sync() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/citations/sync${force ? "?force=true" : ""}`, { method: "POST" });
      if (!res.ok) {
        setMessage(await errorMessage(res));
        return;
      }
      const r: { synced: number; not_found: number } = await res.json();
      setMessage(
        r.synced + r.not_found === 0
          ? "更新が必要な論文はありませんでした"
          : `${r.synced} 本を更新しました${r.not_found ? `（${r.not_found} 本は OpenAlex に見つかりませんでした）` : ""}`,
      );
      startTransition(() => router.refresh());
    } catch {
      setMessage("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <button
        type="button"
        onClick={sync}
        disabled={busy}
        className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-50 dark:border-zinc-700"
      >
        {busy ? "更新中…" : force ? "すべて取得し直す" : "引用の情報を更新"}
      </button>
      {message && <span className="text-zinc-600 dark:text-zinc-400">{message}</span>}
    </div>
  );
}

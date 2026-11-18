"use client";

import Link from "next/link";
import { useState } from "react";

import { BROWSER_API_URL, apiFetch, errorMessage } from "@/lib/api";

// 検索結果や新着の 1 件を登録するボタン。登録済みなら詳細へのリンクになる
export default function RegisterButton({
  arxivId,
  paperId,
}: {
  arxivId: string;
  paperId: number | null;
}) {
  const [id, setId] = useState(paperId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (id !== null) {
    return (
      <Link href={`/papers/${id}`} className="shrink-0 text-sm text-zinc-500 underline">
        登録済み
      </Link>
    );
  }

  async function register() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/papers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arxiv_id: arxivId }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      setId((await res.json()).id);
    } catch {
      setError("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex shrink-0 flex-col items-end gap-1">
      <button
        type="button"
        onClick={register}
        disabled={busy}
        className="rounded bg-zinc-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
      >
        {busy ? "登録中…" : "登録"}
      </button>
      {error && <p className="max-w-48 text-right text-xs text-red-600">{error}</p>}
    </div>
  );
}

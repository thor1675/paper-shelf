"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BROWSER_API_URL, errorMessage } from "@/lib/api";

export default function AddPaperForm() {
  const router = useRouter();
  const [arxivId, setArxivId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!arxivId.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${BROWSER_API_URL}/papers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arxiv_id: arxivId }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      setArxivId("");
      // Server Component（一覧）を取り直す
      router.refresh();
    } catch {
      setError("backend に接続できませんでした");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <div className="flex gap-2">
        <input
          value={arxivId}
          onChange={(e) => setArxivId(e.target.value)}
          placeholder="arXiv ID または URL（例: 1706.03762）"
          className="flex-1 rounded border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
        />
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {submitting ? "取得中…" : "登録"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
}

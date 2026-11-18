"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { BROWSER_API_URL, apiFetch, type BatchItem, errorMessage } from "@/lib/api";

const MAX = 50;

const RESULT_LABELS: Record<BatchItem["result"], string> = {
  created: "登録した",
  exists: "登録済み",
  duplicate: "同じものが上にある",
  invalid: "arXiv ID の形式ではない",
  not_found: "arXiv にない",
  unavailable: "arXiv に繋がらない",
  busy: "arXiv が混んでいる（数分待ってから）",
};

// ID や URL を何行でも貼って、まとめて登録する
export default function BulkAddForm() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [results, setResults] = useState<BatchItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 改行・空白・カンマ・読点で区切る
  const items = text.split(/[\s,、]+/).filter(Boolean);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (items.length === 0 || items.length > MAX) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/papers/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      const body: BatchItem[] = await res.json();
      setResults(body);
      // 登録できたものは欄から消し、うまくいかなかったものだけ残す（直して送り直せるように）
      setText(body.filter((i) => !["created", "exists", "duplicate"].includes(i.result)).map((i) => i.input).join("\n"));
      if (body.some((i) => i.result === "created")) router.refresh();
    } catch {
      setError("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="rounded border border-zinc-200 px-3 py-2 dark:border-zinc-800">
      <summary className="cursor-pointer text-sm text-zinc-600 dark:text-zinc-400">まとめて登録</summary>
      <form onSubmit={submit} className="mt-2 flex flex-col gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          aria-label="まとめて登録する arXiv ID または URL（1 行に 1 件）"
          placeholder={"1 行に 1 件（ID か URL）\n1706.03762\nhttps://arxiv.org/abs/1810.04805"}
          className="rounded border border-zinc-300 bg-transparent p-2 font-mono text-sm dark:border-zinc-700"
        />
        <div className="flex items-center justify-between gap-2">
          <span className={`text-xs ${items.length > MAX ? "text-red-600" : "text-zinc-500"}`}>
            {items.length} 件{items.length > MAX && `（一度に ${MAX} 件まで）`}
          </span>
          <button
            type="submit"
            disabled={busy || items.length === 0 || items.length > MAX}
            className="rounded bg-zinc-900 px-4 py-1.5 text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {busy ? "取得中…" : "まとめて登録"}
          </button>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {results && (
          <ul className="flex flex-col gap-1 text-sm">
            {results.map((r, i) => (
              <li key={i} className="flex gap-2">
                <span
                  className={`shrink-0 ${
                    r.result === "created" ? "font-semibold" : r.result === "exists" || r.result === "duplicate" ? "text-zinc-500" : "text-red-600"
                  }`}
                >
                  {RESULT_LABELS[r.result]}
                </span>
                <span className="min-w-0 break-words text-zinc-600 dark:text-zinc-400">
                  {r.paper_id ? <Link href={`/papers/${r.paper_id}`} className="underline">{r.title}</Link> : r.input}
                </span>
              </li>
            ))}
          </ul>
        )}
      </form>
    </details>
  );
}

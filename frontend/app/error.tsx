"use client"; // エラー画面は Client Component でなければならない

import Link from "next/link";
import { useEffect } from "react";

// どの画面でも、取得に失敗したときは Next.js の素のエラー画面ではなくこれを出す
export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex mx-auto w-full max-w-(--page-max) flex-col gap-4 px-4 py-10">
      <h1 className="text-xl font-bold">表示できませんでした</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        backend が起動しているか確認してください（<code>docker compose ps</code>）
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => retry()}
          className="rounded bg-zinc-900 px-4 py-1.5 text-white dark:bg-zinc-100 dark:text-zinc-900"
        >
          もう一度読み込む
        </button>
        <Link href="/" className="rounded border border-zinc-300 px-4 py-1.5 dark:border-zinc-700">
          一覧へ
        </Link>
      </div>
    </main>
  );
}

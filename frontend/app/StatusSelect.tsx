"use client";

import { useRouter } from "next/navigation";
import { useOptimistic, useTransition } from "react";

import {
  BROWSER_API_URL,
  STATUSES,
  STATUS_LABELS,
  type Status,
  errorMessage,
} from "@/lib/api";

// 一覧のカードで、選んだ瞬間にステータスを保存する
export default function StatusSelect({
  paperId,
  title,
  status,
}: {
  paperId: number;
  title: string;
  status: Status;
}) {
  const router = useRouter();
  // 保存と一覧の取り直しが終わるまでの間も、選んだ値を表示しておく（終わると status に戻る）。
  // 失敗したときは、取り直しが起きないので元の値に戻る
  const [shown, setShown] = useOptimistic(status);
  const [pending, startTransition] = useTransition();

  function handleChange(next: Status) {
    startTransition(async () => {
      setShown(next);
      try {
        const res = await fetch(`${BROWSER_API_URL}/papers/${paperId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: next }),
        });
        if (!res.ok) {
          alert(await errorMessage(res));
          return;
        }
        router.refresh();
      } catch {
        alert("backend に接続できませんでした");
      }
    });
  }

  return (
    <select
      value={shown}
      disabled={pending}
      aria-label={`「${title}」の状態`}
      onChange={(e) => handleChange(e.target.value as Status)}
      className="shrink-0 rounded bg-zinc-100 px-2 py-0.5 text-xs disabled:opacity-70 dark:bg-zinc-800"
    >
      {STATUSES.map((s) => (
        <option key={s} value={s}>
          {STATUS_LABELS[s]}
        </option>
      ))}
    </select>
  );
}

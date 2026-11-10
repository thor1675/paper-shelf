"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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
  status,
}: {
  paperId: number;
  status: Status;
}) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);

  async function handleChange(next: Status) {
    setSaving(true);
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
    } finally {
      setSaving(false);
    }
  }

  return (
    <select
      value={status}
      disabled={saving}
      onChange={(e) => handleChange(e.target.value as Status)}
      className="shrink-0 rounded bg-zinc-100 px-2 py-0.5 text-xs disabled:opacity-50 dark:bg-zinc-800"
    >
      {STATUSES.map((s) => (
        <option key={s} value={s}>
          {STATUS_LABELS[s]}
        </option>
      ))}
    </select>
  );
}

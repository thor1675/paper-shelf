"use client";

import { useState } from "react";

import { BROWSER_API_URL, apiFetch, errorMessage } from "@/lib/api";

// ログインと新規登録の入力欄。成功したら画面ごと読み直す（上のメニューにユーザー名を出すため）
export default function AuthForm({
  mode,
  next,
  needsInvite = false,
}: {
  mode: "login" | "register";
  next: string;
  needsInvite?: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body: Record<string, string> = {
      username: String(form.get("username") ?? "").trim(),
      password: String(form.get("password") ?? ""),
    };
    if (mode === "register" && needsInvite) body.invite_code = String(form.get("invite_code") ?? "").trim();
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      window.location.assign(next);
    } catch {
      setError("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  const input = "rounded border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700";
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        ユーザー名
        <input name="username" required autoComplete="username" className={input} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        パスワード{mode === "register" && <span className="text-xs text-zinc-500">8 文字以上</span>}
        <input
          name="password"
          type="password"
          required
          minLength={mode === "register" ? 8 : undefined}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          className={input}
        />
      </label>
      {mode === "register" && needsInvite && (
        <label className="flex flex-col gap-1 text-sm">
          招待コード
          <input name="invite_code" required autoComplete="off" className={`${input} font-mono uppercase`} />
        </label>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
      >
        {busy ? "送信中…" : mode === "login" ? "ログイン" : "登録"}
      </button>
    </form>
  );
}

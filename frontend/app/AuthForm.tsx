"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="username">ユーザー名</Label>
        <Input id="username" name="username" required autoComplete="username" />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="password">
          パスワード{mode === "register" && <span className="text-xs font-normal text-muted-foreground">8 文字以上</span>}
        </Label>
        <Input
          id="password"
          name="password"
          type="password"
          required
          minLength={mode === "register" ? 8 : undefined}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
        />
      </div>
      {mode === "register" && needsInvite && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="invite_code">招待コード</Label>
          <Input id="invite_code" name="invite_code" required autoComplete="off" className="font-mono uppercase" />
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={busy}>
        {busy ? "送信中…" : mode === "login" ? "ログイン" : "登録"}
      </Button>
    </form>
  );
}

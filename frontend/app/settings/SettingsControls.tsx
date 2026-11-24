"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useConfirm } from "@/components/useConfirm";
import { GitHubMark } from "@/components/GitHubMark";
import { SlackMark } from "@/components/SlackMark";
import { Button } from "@/components/ui/button";
import { BROWSER_API_URL, apiFetch, errorMessage, githubStartUrl } from "@/lib/api";

type Code = { code: string; expires_at: string };

const time = (iso: string) =>
  new Date(iso).toLocaleString("ja-JP", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });

export function LogoutButton() {
  async function logout() {
    await apiFetch(`${BROWSER_API_URL}/auth/logout`, { method: "POST" }).catch(() => null);
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }
  return (
    <button type="button" onClick={logout} className="rounded border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700">
      ログアウト
    </button>
  );
}

export function SlackLinkBox({ linked }: { linked: boolean }) {
  const { confirm: ask, dialog } = useConfirm();
  const router = useRouter();
  const [code, setCode] = useState<Code | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function issue() {
    setError(null);
    const res = await apiFetch(`${BROWSER_API_URL}/auth/slack-link-code`, { method: "POST" }).catch(() => null);
    if (!res) setError("backend に接続できませんでした");
    else if (!res.ok) setError(await errorMessage(res));
    else setCode(await res.json());
  }

  async function unlink() {
    if (!(await ask({ title: "Slack との紐づけを解除しますか？", description: "解除すると、Slack に貼ったリンクや新着通知の「保存」があなたの本棚に保存されなくなります", action: "解除", destructive: true }))) return;
    const res = await apiFetch(`${BROWSER_API_URL}/auth/slack-link`, { method: "DELETE" }).catch(() => null);
    if (res?.ok) router.refresh();
    else setError(res ? await errorMessage(res) : "backend に接続できませんでした");
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      {dialog}
      {linked ? (
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5">
            <SlackMark />
            Slack と紐づけ済み
          </span>
          <Button variant="link" size="sm" className="text-muted-foreground" onClick={unlink}>
            紐づけを解除
          </Button>
        </div>
      ) : (
        <div>
          <Button variant="outline" size="sm" onClick={issue}>
            <SlackMark />
            紐づけのコードを発行
          </Button>
        </div>
      )}
      {code && !linked && (
        <div className="flex flex-col gap-1 rounded border border-zinc-200 p-3 dark:border-zinc-800">
          <p>
            PAPER - Shelf のボットがいる Slack のチャンネルに、次のコードをそのまま投稿してください（{time(code.expires_at)} まで有効）
          </p>
          <code className="text-base font-semibold select-all">{code.code}</code>
          <p className="text-xs text-zinc-500">投稿したら、この画面を再読み込みすると「紐づけ済み」になります</p>
        </div>
      )}
      {error && <p className="text-red-600">{error}</p>}
    </div>
  );
}

export function InviteBox({ initial }: { initial: Code[] }) {
  const [codes, setCodes] = useState(initial);
  const [error, setError] = useState<string | null>(null);

  async function issue() {
    setError(null);
    const res = await apiFetch(`${BROWSER_API_URL}/auth/invites`, { method: "POST" }).catch(() => null);
    if (!res) setError("backend に接続できませんでした");
    else if (!res.ok) setError(await errorMessage(res));
    else setCodes([...codes, await res.json()]);
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div>
        <button type="button" onClick={issue} className="rounded border border-zinc-300 px-3 py-1 dark:border-zinc-700">
          招待コードを発行
        </button>
      </div>
      {codes.length > 0 && (
        <ul className="flex flex-col gap-1">
          {codes.map((c) => (
            <li key={c.code}>
              <code className="font-semibold select-all">{c.code}</code>
              <span className="ml-2 text-xs text-zinc-500">{time(c.expires_at)} まで</span>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="text-red-600">{error}</p>}
    </div>
  );
}

const input = "rounded border border-zinc-300 px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900";

export function AccountBox({ username }: { username: string }) {
  const router = useRouter();
  const [name, setName] = useState(username);
  const [nameCurrent, setNameCurrent] = useState("");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmNext, setConfirmNext] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(path: string, method: string, body: object, done: string) {
    setBusy(true);
    setMessage(null);
    const res = await apiFetch(`${BROWSER_API_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    setBusy(false);
    if (!res) setMessage({ ok: false, text: "backend に接続できませんでした" });
    else if (!res.ok) setMessage({ ok: false, text: await errorMessage(res) });
    else {
      setMessage({ ok: true, text: done });
      return true;
    }
    return false;
  }

  async function changeName(e: React.FormEvent) {
    e.preventDefault();
    if (await send("/auth/username", "PATCH", { username: name, current_password: nameCurrent }, "ユーザー名を変更しました")) {
      setNameCurrent("");
      router.refresh();
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    if (next !== confirmNext) {
      setMessage({ ok: false, text: "新しいパスワードが確認用と一致しません" });
      return;
    }
    const ok = await send(
      "/auth/password",
      "POST",
      { current_password: current, new_password: next },
      "パスワードを変更しました。ほかの端末ではログインし直してください",
    );
    if (ok) {
      setCurrent("");
      setNext("");
      setConfirmNext("");
    }
  }

  return (
    <div className="flex flex-col gap-4 text-sm">
      <form onSubmit={changeName} className="flex flex-col gap-2">
        <h3 className="font-semibold">ユーザー名を変更</h3>
        <label className="flex flex-col gap-1">
          新しいユーザー名（半角英数字と _ - で 3〜32 文字）
          <input className={input} value={name} onChange={(e) => setName(e.target.value)} autoComplete="username" required />
        </label>
        <label className="flex flex-col gap-1">
          今のパスワード
          <input
            className={input}
            type="password"
            value={nameCurrent}
            onChange={(e) => setNameCurrent(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <div>
          <button type="submit" disabled={busy || name === username} className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-50 dark:border-zinc-700">
            ユーザー名を変更
          </button>
        </div>
      </form>

      <form onSubmit={changePassword} className="flex flex-col gap-2">
        <h3 className="font-semibold">パスワードを変更</h3>
        <label className="flex flex-col gap-1">
          今のパスワード
          <input className={input} type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </label>
        <label className="flex flex-col gap-1">
          新しいパスワード（8 文字以上）
          <input className={input} type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={8} required />
        </label>
        <label className="flex flex-col gap-1">
          新しいパスワード（確認用）
          <input className={input} type="password" value={confirmNext} onChange={(e) => setConfirmNext(e.target.value)} autoComplete="new-password" required />
        </label>
        <div>
          <button type="submit" disabled={busy} className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-50 dark:border-zinc-700">
            パスワードを変更
          </button>
        </div>
      </form>

      {message && <p className={message.ok ? "text-green-700 dark:text-green-400" : "text-red-600"}>{message.text}</p>}
    </div>
  );
}

export function GitHubLinkBox({ login, enabled }: { login: string | null; enabled: boolean }) {
  const router = useRouter();
  const { confirm: ask, dialog } = useConfirm();
  const [error, setError] = useState<string | null>(null);

  async function unlink() {
    if (!(await ask({ title: "GitHub との紐づけを解除しますか？", description: "解除すると「GitHub でログイン」が使えなくなります。ユーザー名とパスワードでのログインはそのまま使えます", action: "解除", destructive: true }))) return;
    const res = await apiFetch(`${BROWSER_API_URL}/auth/github-link`, { method: "DELETE" }).catch(() => null);
    if (res?.ok) router.replace("/settings");
    else setError(res ? await errorMessage(res) : "backend に接続できませんでした");
    router.refresh();
  }

  if (!enabled && !login) return <p className="text-sm text-muted-foreground">この PAPER - Shelf では GitHub でのログインが設定されていません（README の「GitHub でログイン」）</p>;
  return (
    <div className="flex flex-col gap-2 text-sm">
      {dialog}
      {login ? (
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5">
            <GitHubMark />
            {login} と紐づけ済み
          </span>
          <Button variant="link" size="sm" className="text-muted-foreground" onClick={unlink}>
            紐づけを解除
          </Button>
        </div>
      ) : (
        <div>
          {/* GitHub の画面へ移るので、普通のリンクにする */}
          <Button variant="outline" size="sm" asChild>
            <a href={githubStartUrl("link", "/settings")}>
              <GitHubMark />
              GitHub と紐づける
            </a>
          </Button>
        </div>
      )}
      {error && <p className="text-destructive">{error}</p>}
    </div>
  );
}

import Link from "next/link";
import { unstable_rethrow } from "next/navigation";

import type { Me } from "@/lib/api";
import { serverFetch } from "@/lib/server";

import { AccountBox } from "../SettingsControls";

export default async function AccountPage() {
  let me: Me | null = null;
  try {
    const res = await serverFetch("/auth/me");
    if (res.ok) me = await res.json();
  } catch (e) {
    unstable_rethrow(e);
  }
  if (!me) return <main className="mx-auto w-full max-w-3xl px-4 py-10 text-red-600">backend に接続できませんでした</main>;
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <Link href="/settings" className="text-sm text-zinc-500 hover:underline">
        ← 設定に戻る
      </Link>
      <h1 className="text-2xl font-bold">ユーザー名とパスワード</h1>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">今のユーザー名: {me.username}</p>
      <AccountBox username={me.username} />
    </main>
  );
}

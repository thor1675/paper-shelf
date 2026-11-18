import Link from "next/link";
import { unstable_rethrow } from "next/navigation";

import type { Me } from "@/lib/api";
import { serverFetch } from "@/lib/server";

import { InviteBox, LogoutButton, SlackLinkBox } from "./SettingsControls";

type Code = { code: string; expires_at: string };

export default async function SettingsPage() {
  let me: Me | null = null;
  let invites: Code[] = [];
  try {
    const [m, i] = await Promise.all([serverFetch("/auth/me"), serverFetch("/auth/invites")]);
    if (m.ok) me = await m.json();
    if (i.ok) invites = await i.json();
  } catch (e) {
    unstable_rethrow(e);
  }
  if (!me) return <main className="mx-auto w-full max-w-3xl px-4 py-10 text-red-600">backend に接続できませんでした</main>;
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">設定</h1>
        <LogoutButton />
      </div>
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-bold">アカウント</h2>
        <div className="flex items-center gap-3 text-sm">
          <span>ユーザー名: {me.username}</span>
          <Link href="/settings/account" className="rounded border border-zinc-300 px-3 py-1 dark:border-zinc-700">
            ユーザー名・パスワードを変更 →
          </Link>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-bold">Slack との紐づけ</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          紐づけると、Slack に貼った arXiv のリンクと、新着通知の「保存」があなたの本棚に入ります。新着通知ではあなたがメンションされます。紐づけていない人の投稿は保存されません
        </p>
        <SlackLinkBox linked={me.slack_linked} />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-bold">招待コード</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          ほかの人が登録するときに必要です。1 つのコードで 1 人だけ登録でき、7 日で使えなくなります
        </p>
        <InviteBox initial={invites} />
      </section>
    </main>
  );
}

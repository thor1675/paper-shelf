import Link from "next/link";
import { cookies } from "next/headers";
import { unstable_rethrow } from "next/navigation";

import { GITHUB_ERRORS, type Me } from "@/lib/api";
import { DISPLAY_COOKIE, parseDisplay } from "@/lib/display";
import { serverFetch } from "@/lib/server";

import DisplaySettings from "./DisplaySettings";
import { GitHubLinkBox, InviteBox, LogoutButton, SlackLinkBox } from "./SettingsControls";

type Code = { code: string; expires_at: string };

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ github?: string; github_error?: string }>;
}) {
  const { github, github_error } = await searchParams;
  let githubEnabled = false;
  let me: Me | null = null;
  let invites: Code[] = [];
  try {
    const [m, i, setup] = await Promise.all([serverFetch("/auth/me"), serverFetch("/auth/invites"), serverFetch("/auth/setup")]);
    if (m.ok) me = await m.json();
    if (i.ok) invites = await i.json();
    if (setup.ok) githubEnabled = (await setup.json()).github_enabled;
  } catch (e) {
    unstable_rethrow(e);
  }
  if (!me) return <main className="mx-auto w-full max-w-(--page-max) px-4 py-10 text-red-600">backend に接続できませんでした</main>;
  return (
    <main className="flex mx-auto w-full max-w-(--page-max) flex-col gap-8 px-4 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">設定</h1>
        <LogoutButton />
      </div>
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-bold">アカウント</h2>
        <div className="flex items-center gap-3 text-sm">
          <span>ユーザー名: {me.username}</span>
          <Link href="/settings/security" className="rounded border border-zinc-300 px-3 py-1 dark:border-zinc-700">
            セキュリティ設定 →
          </Link>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-bold">表示</h2>
        <DisplaySettings initial={parseDisplay((await cookies()).get(DISPLAY_COOKIE)?.value)} />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-bold">GitHub との紐づけ</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          紐づけると、ログイン画面の「GitHub でログイン」で入れます。PAPER - Shelf は GitHub の公開されている名前と ID だけを受け取り、パスワードやリポジトリには触れません
        </p>
        {github === "linked" && <p className="text-sm text-green-700 dark:text-green-400">GitHub と紐づけました</p>}
        {github_error && <p role="alert" className="text-sm text-destructive">{GITHUB_ERRORS[github_error] ?? GITHUB_ERRORS.github}</p>}
        <GitHubLinkBox login={me.github_login} enabled={githubEnabled} />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-bold">Slack との紐づけ</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          紐づけると、Slack に貼った arXiv のリンクと、新着通知で「保存」を押した論文があなたの本棚に保存されます
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

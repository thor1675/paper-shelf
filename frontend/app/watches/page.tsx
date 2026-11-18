import Link from "next/link";
import { connection } from "next/server";

import { type SearchItem, type Watch } from "@/lib/api";

import SearchResultList from "../SearchResultList";
import { AddWatchForm, DeleteWatchButton } from "./WatchControls";
import { unstable_rethrow } from "next/navigation";
import { serverFetch } from "@/lib/server";

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", dateStyle: "short", timeStyle: "short" });
}

export default async function WatchesPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  await connection();
  const sp = await searchParams;
  const checkId = Number(Array.isArray(sp.check) ? sp.check[0] : sp.check) || null;

  let watches: Watch[] | null = null;
  try {
    const res = await serverFetch(`/watches`);
    if (res.ok) watches = await res.json();
  } catch (e) {
    unstable_rethrow(e);
    // 下で表示する
  }

  // 「新着を見る」を押したキーワードだけ、arXiv に問い合わせる
  let fresh: SearchItem[] | null = null;
  let freshError: string | null = null;
  const checking = watches?.find((w) => w.id === checkId);
  if (checking) {
    try {
      const res = await serverFetch(`/watches/${checking.id}/new`);
      const body = await res.json();
      if (res.ok) fresh = body;
      else freshError = typeof body.detail === "string" ? body.detail : `エラーが発生しました（${res.status}）`;
    } catch (e) {
    unstable_rethrow(e);
      freshError = "backend に接続できませんでした";
    }
  }

  return (
    <main className="flex mx-auto w-full max-w-(--page-max) flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-bold">新着</h1>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        登録したキーワードで、毎朝 9 時に arXiv の新着を調べて Slack に知らせます（Slack を設定している場合）。
        「新着を見る」にていつでも確認できます。一度 Slack で知らせた論文と、登録済みの論文は表示されません
      </p>

      <AddWatchForm />

      {watches === null ? (
        <p className="text-red-600">キーワードを取得できませんでした。backend が起動しているか確認してください</p>
      ) : watches.length === 0 ? (
        <p className="text-zinc-500">まだキーワードがありません</p>
      ) : (
        <ul className="flex flex-col divide-y divide-zinc-200 rounded border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          {watches.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
              <div className="min-w-0">
                <p className="font-semibold break-words">{w.query}</p>
                <p className="text-xs text-zinc-500">
                  {w.notified_at ? `前回の通知 ${formatDateTime(w.notified_at)}` : "まだ通知していません"}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Link
                  href={`/watches?check=${w.id}`}
                  aria-current={w.id === checkId ? "true" : undefined}
                  className="text-sm underline"
                >
                  新着を見る
                </Link>
                <DeleteWatchButton id={w.id} query={w.query} />
              </div>
            </li>
          ))}
        </ul>
      )}

      {checking && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-bold break-words">「{checking.query}」の新着</h2>
          {freshError ? (
            <p className="text-red-600">{freshError}</p>
          ) : fresh && fresh.length === 0 ? (
            <p className="text-zinc-500">新しい論文はありません</p>
          ) : (
            fresh && <SearchResultList items={fresh} />
          )}
        </section>
      )}
    </main>
  );
}

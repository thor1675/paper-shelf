import { connection } from "next/server";

import { type TagCount } from "@/lib/api";

import TagRow from "./TagRow";
import { unstable_rethrow } from "next/navigation";
import { serverFetch } from "@/lib/server";

export default async function TagsPage() {
  await connection();
  let tags: TagCount[] | null = null;
  try {
    const res = await serverFetch(`/tags`);
    if (res.ok) tags = await res.json();
  } catch (e) {
    unstable_rethrow(e);
    // 下で表示する
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-bold">タグ</h1>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        名前を変えられます。既にあるタグの名前にすると、2 つのタグが 1 つにまとまります（「指示追従」と「意図追従」など）。
        「外す」はタグを全部の論文から外すだけで、論文は消えません
      </p>
      {tags === null ? (
        <p className="text-red-600">タグを取得できませんでした。backend が起動しているか確認してください</p>
      ) : tags.length === 0 ? (
        <p className="text-zinc-500">まだタグがありません</p>
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-zinc-200 rounded border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
            {tags.map((t) => (
              <TagRow key={t.name} name={t.name} count={t.count} others={tags.map((x) => x.name)} />
            ))}
          </ul>
          <datalist id="tag-names">
            {tags.map((t) => (
              <option key={t.name} value={t.name} />
            ))}
          </datalist>
        </>
      )}
    </main>
  );
}

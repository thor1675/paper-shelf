import Link from "next/link";
import { redirect } from "next/navigation";

import { getMe } from "@/lib/server";

import AuthForm from "../AuthForm";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  // ログイン中ならそのまま一覧へ
  if (await getMe()) redirect(safeNext(next));
  return (
    <main className="mx-auto flex w-full max-w-sm flex-col gap-6 px-4 py-16">
      <h1 className="text-2xl font-bold">ログイン</h1>
      <AuthForm mode="login" next={safeNext(next)} />
      <p className="text-sm text-zinc-500">
        アカウントが無い場合は{" "}
        <Link href="/register" className="underline">
          新規登録
        </Link>
      </p>
    </main>
  );
}

// ほかのサイトへ移されないよう、アプリの中のパスだけを受け付ける
function safeNext(next: string | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

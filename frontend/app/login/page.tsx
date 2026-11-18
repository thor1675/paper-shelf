import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { GITHUB_ERRORS, SERVER_API_URL, githubStartUrl } from "@/lib/api";
import { getMe } from "@/lib/server";

import AuthForm from "../AuthForm";
import { GitHubMark } from "@/components/GitHubMark";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; github_error?: string }>;
}) {
  const { next, github_error } = await searchParams;
  // ログイン中ならそのまま一覧へ
  if (await getMe()) redirect(safeNext(next));
  let githubEnabled = false;
  try {
    const res = await fetch(`${SERVER_API_URL}/auth/setup`, { cache: "no-store" });
    githubEnabled = res.ok && (await res.json()).github_enabled;
  } catch {
    // backend に繋がらないときは GitHub のボタンを出さない（ログインのときにエラーが出る）
  }
  const githubError = github_error ? (GITHUB_ERRORS[github_error] ?? GITHUB_ERRORS.github) : null;
  return (
    <main className="mx-auto flex w-full max-w-sm flex-col px-4 py-16">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">ログイン</CardTitle>
          <CardDescription>PAPER - Shelf を使うにはログインしてください</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {githubError && (
            <p role="alert" className="text-sm text-destructive">
              {githubError}
            </p>
          )}
          <AuthForm mode="login" next={safeNext(next)} />
          {githubEnabled && (
            <>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                または
                <span className="h-px flex-1 bg-border" />
              </div>
              {/* GitHub の画面へ移るので、Next.js の Link ではなく普通のリンクにする */}
              <Button variant="outline" asChild>
                <a href={githubStartUrl("login", safeNext(next))}>
                  <GitHubMark />
                  GitHub でログイン
                </a>
              </Button>
            </>
          )}
        </CardContent>
        <CardFooter className="text-sm text-muted-foreground">
          アカウントが無い場合は
          <Link href="/register" className="ml-1 underline">
            新規登録
          </Link>
        </CardFooter>
      </Card>
    </main>
  );
}

// ほかのサイトへ移されないよう、アプリの中のパスだけを受け付ける
function safeNext(next: string | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

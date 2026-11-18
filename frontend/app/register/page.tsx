import Link from "next/link";
import { redirect } from "next/navigation";

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { SERVER_API_URL } from "@/lib/api";
import { getMe } from "@/lib/server";

import AuthForm from "../AuthForm";

export default async function RegisterPage() {
  if (await getMe()) redirect("/");
  let needsSetup = false;
  try {
    const res = await fetch(`${SERVER_API_URL}/auth/setup`, { cache: "no-store" });
    needsSetup = res.ok && (await res.json()).needs_setup;
  } catch {
    // backend に繋がらないときは招待コードの欄を出しておく（登録のときにエラーが出る）
  }
  return (
    <main className="mx-auto flex w-full max-w-sm flex-col px-4 py-16">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">新規登録</CardTitle>
          <CardDescription>
            {needsSetup
              ? "最初の利用者です。登録すると、これまでに登録された論文と新着のキーワードを引き継ぎます"
              : "登録には招待コードが必要です。登録済みの人に、設定画面から招待コードを発行してもらってください"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AuthForm mode="register" needsInvite={!needsSetup} next="/" />
        </CardContent>
        <CardFooter className="text-sm text-muted-foreground">
          アカウントがある場合は
          <Link href="/login" className="ml-1 underline">
            ログイン
          </Link>
        </CardFooter>
      </Card>
    </main>
  );
}

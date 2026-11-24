// ログインの Cookie が無ければ、ログイン画面へ回す（Cookie が本物かどうかは backend が確かめる）
import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/api";

const PUBLIC = ["/login", "/register"];

export default function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (PUBLIC.some((p) => pathname === p) || req.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const url = new URL("/login", req.url);
  if (pathname !== "/") url.searchParams.set("next", pathname + search);
  return NextResponse.redirect(url);
}

export const config = {
  // 画像や JS などの静的なファイルには使わない。
  // /api は backend への中継（公開版）で、ログインの確認は backend がする（ここで回すと API の応答がログイン画面になる）
  matcher: ["/((?!api/|_next/static|_next/image|favicon.ico|.*\\.(?:png|svg|ico)$).*)"],
};

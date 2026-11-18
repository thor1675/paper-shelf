// Server Component から backend を呼ぶ。ブラウザから届いたログインの Cookie をそのまま backend に渡す
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { type Me, SERVER_API_URL, SESSION_COOKIE } from "./api";

async function withSession(init?: RequestInit): Promise<RequestInit> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const headers = new Headers(init?.headers);
  if (token) headers.set("Cookie", `${SESSION_COOKIE}=${token}`);
  return { ...init, headers, cache: "no-store" };
}

// ログインが切れていたら（401）ログイン画面へ移る。
// redirect は例外で移動するので、呼ぶ側の catch では unstable_rethrow(e) で投げ直す
export async function serverFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${SERVER_API_URL}${path}`, await withSession(init));
  if (res.status === 401) redirect("/login");
  return res;
}

// ログイン中の人。ログインしていなければ null（ログイン画面でも使うので移動しない）
export async function getMe(): Promise<Me | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/auth/me`, await withSession());
    return res.ok ? ((await res.json()) as Me) : null;
  } catch {
    return null;
  }
}

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "katex/dist/katex.min.css";
import "./globals.css";
import { cookies } from "next/headers";

import { DISPLAY_COOKIE, parseDisplay } from "@/lib/display";
import { getMe } from "@/lib/server";

import Nav from "./Nav";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PAPER - Shelf",
  description: "arXiv の論文を整理する",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // 上のメニューにユーザー名を出す（ログイン画面では null）
  const me = await getMe();
  // 表示の設定（文字の大きさ・幅・テーマ）。globals.css が data-* 属性を見て切り替える
  const display = parseDisplay((await cookies()).get(DISPLAY_COOKIE)?.value);
  return (
    <html
      lang="ja"
      data-font={display.font}
      data-width={display.width}
      data-theme={display.theme}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Nav username={me?.username ?? null} />
        {children}
      </body>
    </html>
  );
}

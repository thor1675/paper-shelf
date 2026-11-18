import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "katex/dist/katex.min.css";
import "./globals.css";
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
  return (
    <html
      lang="ja"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Nav username={me?.username ?? null} />
        {children}
      </body>
    </html>
  );
}

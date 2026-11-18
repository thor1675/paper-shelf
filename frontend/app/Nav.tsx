"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { confirmLeave } from "@/lib/unsaved";

const LINKS = [
  { href: "/", label: "一覧" },
  { href: "/search", label: "arXiv 検索" },
  { href: "/watches", label: "新着" },
  { href: "/citations", label: "引用図" },
  { href: "/tags", label: "タグ" },
  { href: "/insights", label: "図解" },
];

// 全画面に共通のナビゲーション。詳細画面で編集中なら、移動する前に確認する
export default function Nav({ username }: { username: string | null }) {
  const pathname = usePathname();
  return (
    <nav className="border-b border-zinc-200 dark:border-zinc-800">
      <div className="flex mx-auto w-full max-w-(--page-max) flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
        <Link
          href="/"
          className="mr-2 font-bold"
          onNavigate={(e) => {
            if (!confirmLeave()) e.preventDefault();
          }}
        >
          PAPER - Shelf
        </Link>
        {/* ログインしていないとき（ログイン画面）はメニューを出さない */}
        {username && LINKS.map((l) => {
          const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              aria-current={active ? "page" : undefined}
              className={`text-sm ${active ? "font-semibold" : "text-zinc-500 hover:underline"}`}
              onNavigate={(e) => {
                if (!confirmLeave()) e.preventDefault();
              }}
            >
              {l.label}
            </Link>
          );
        })}
        {username && (
          <Link
            href="/settings"
            aria-current={pathname.startsWith("/settings") ? "page" : undefined}
            className={`ml-auto text-sm ${pathname.startsWith("/settings") ? "font-semibold" : "text-zinc-500 hover:underline"}`}
            onNavigate={(e) => {
              if (!confirmLeave()) e.preventDefault();
            }}
          >
            {username}（設定）
          </Link>
        )}
      </div>
    </nav>
  );
}

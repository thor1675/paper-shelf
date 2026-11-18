"use client";

import { useEffect, useState } from "react";

import { BROWSER_API_URL, apiFetch, type CitationNode, errorMessage } from "@/lib/api";

import CitationTable from "../../citations/CitationTable";

// 似ている論文（OpenAlex が分野や内容の近さで選んだもの）。
// OpenAlex への問い合わせで詳細画面の表示を待たせないよう、画面が出てから取りに行く
export default function RelatedPapers({ arxivId }: { arxivId: string }) {
  const [items, setItems] = useState<CitationNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`${BROWSER_API_URL}/citations/related?key=${encodeURIComponent(arxivId)}`)
      .then(async (res) => {
        if (cancelled) return;
        if (res.ok) setItems(await res.json());
        else setError(await errorMessage(res));
      })
      .catch(() => !cancelled && setError("backend に接続できませんでした"));
    return () => {
      cancelled = true;
    };
  }, [arxivId]);

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-bold">おすすめの論文</h2>
      {error ? (
        <p className="text-sm text-zinc-500">{error}</p>
      ) : items === null ? (
        <p className="text-sm text-zinc-500">読み込み中…</p>
      ) : (
        <CitationTable nodes={items} empty="おすすめの論文はありません" />
      )}
    </section>
  );
}

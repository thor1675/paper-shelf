import { notFound } from "next/navigation";

import { type Paper, SERVER_API_URL, type TagCount } from "@/lib/api";

import PaperDetail from "./PaperDetail";

export default async function PaperPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [paperRes, tagsRes] = await Promise.all([
    fetch(`${SERVER_API_URL}/papers/${encodeURIComponent(id)}`),
    // タグの候補が取れなくても、論文の表示はできるようにする
    fetch(`${SERVER_API_URL}/tags`).catch(() => null),
  ]);
  // 存在しない id と、数字でない id（backend は 422 を返す）はどちらも 404 ページにする
  if (paperRes.status === 404 || paperRes.status === 422) notFound();
  if (!paperRes.ok) throw new Error(`論文を取得できませんでした（${paperRes.status}）`);

  const paper: Paper = await paperRes.json();
  const allTags: TagCount[] = tagsRes?.ok ? await tagsRes.json() : [];

  // key: 別の論文に移ったときに、前の論文の表示や編集中の内容を持ち越さない
  return <PaperDetail key={paper.id} paper={paper} allTags={allTags.map((t) => t.name)} />;
}

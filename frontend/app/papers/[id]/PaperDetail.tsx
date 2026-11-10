"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Markdown from "@/app/Markdown";
import {
  BROWSER_API_URL,
  type Paper,
  STATUSES,
  STATUS_LABELS,
  type Status,
  addTag,
  errorMessage,
} from "@/lib/api";

type Draft = { status: Status; tags: string[]; note: string };

const UNSAVED_MESSAGE = "変更が保存されていません。破棄して移動しますか？";

export default function PaperDetail({
  paper,
  allTags,
}: {
  paper: Paper;
  allTags: string[];
}) {
  const router = useRouter();
  // draft が null なら表示モード、値があれば編集モード
  const [draft, setDraft] = useState<Draft | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [noteTab, setNoteTab] = useState<"write" | "preview">("write");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const dirty =
    draft !== null &&
    (draft.status !== paper.status ||
      draft.note !== paper.note ||
      draft.tags.join("\n") !== paper.tags.join("\n") ||
      tagInput.trim() !== "");

  // タブを閉じる・再読み込みするときの警告
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  function startEdit() {
    setDraft({ status: paper.status, tags: paper.tags, note: paper.note });
    setTagInput("");
    setNoteTab("write");
    setError(null);
  }

  function cancelEdit() {
    if (dirty && !confirm("変更を破棄しますか？")) return;
    setDraft(null);
    setError(null);
  }

  function commitTagInput() {
    if (!draft) return;
    setDraft({ ...draft, tags: addTag(draft.tags, tagInput) });
    setTagInput("");
  }

  async function save() {
    if (!draft) return;
    // 入力欄に残っているタグも保存に含める
    const tags = addTag(draft.tags, tagInput);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${BROWSER_API_URL}/papers/${paper.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...draft, tags }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      setDraft(null);
      setTagInput("");
      router.refresh();
    } catch {
      setError("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  // 表示モードでチェックボックスを押したとき。メモだけをその場で保存する
  async function saveNote(note: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${BROWSER_API_URL}/papers/${paper.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      router.refresh();
    } catch {
      setError("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`「${paper.title}」を削除しますか？`)) return;
    setBusy(true);
    try {
      const res = await fetch(`${BROWSER_API_URL}/papers/${paper.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      router.replace("/");
      router.refresh();
    } catch {
      setError("backend に接続できませんでした");
    } finally {
      setBusy(false);
    }
  }

  const suggestions = allTags.filter((t) => !draft?.tags.includes(t));

  const abstractSection = (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-bold">Abstract</h2>
      <p className="leading-7 text-zinc-700 dark:text-zinc-300">{paper.abstract}</p>
    </section>
  );

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      <Link
        href="/"
        className="text-sm text-zinc-500 hover:underline"
        onNavigate={(e) => {
          if (dirty && !confirm(UNSAVED_MESSAGE)) e.preventDefault();
        }}
      >
        ← 一覧へ
      </Link>

      <header className="flex flex-col gap-2">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-2xl font-bold">{paper.title}</h1>
          {!draft && (
            <span className="shrink-0 rounded bg-zinc-100 px-2 py-0.5 text-sm dark:bg-zinc-800">
              {STATUS_LABELS[paper.status]}
            </span>
          )}
        </div>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {paper.authors.join(", ")}
        </p>
        <p className="flex flex-wrap gap-x-3 text-sm text-zinc-600 dark:text-zinc-400">
          <span>{paper.published}</span>
          <span>arXiv:{paper.arxiv_id}</span>
          <a href={paper.arxiv_url} target="_blank" rel="noopener noreferrer" className="underline">
            arXiv
          </a>
          <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer" className="underline">
            PDF
          </a>
        </p>
      </header>

      {draft ? (
        <>
          <section className="flex flex-col gap-4 rounded border border-zinc-300 p-4 dark:border-zinc-700">
            <label className="flex items-center gap-3">
              <span className="w-12 text-sm font-semibold">状態</span>
              <select
                value={draft.status}
                onChange={(e) => setDraft({ ...draft, status: e.target.value as Status })}
                className="rounded border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex items-start gap-3">
              <span className="w-12 pt-1 text-sm font-semibold">タグ</span>
              <div className="flex flex-1 flex-wrap items-center gap-1">
                {draft.tags.map((t) => (
                  <span
                    key={t}
                    className="flex items-center gap-1 rounded-full bg-zinc-100 px-2 py-0.5 text-sm dark:bg-zinc-800"
                  >
                    {t}
                    <button
                      type="button"
                      aria-label={`${t} を外す`}
                      onClick={() =>
                        setDraft({ ...draft, tags: draft.tags.filter((x) => x !== t) })
                      }
                      className="text-zinc-500 hover:text-red-600"
                    >
                      ×
                    </button>
                  </span>
                ))}
                <input
                  value={tagInput}
                  list="tag-suggestions"
                  placeholder="タグを追加（Enter）"
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    // 日本語入力の変換確定の Enter ではタグを追加しない
                    if (e.nativeEvent.isComposing) return;
                    if (e.key === "Enter" || e.key === ",") {
                      e.preventDefault();
                      commitTagInput();
                    } else if (e.key === "Backspace" && tagInput === "" && draft.tags.length > 0) {
                      setDraft({ ...draft, tags: draft.tags.slice(0, -1) });
                    }
                  }}
                  className="min-w-40 flex-1 bg-transparent px-1 py-0.5 text-sm outline-none"
                />
                <datalist id="tag-suggestions">
                  {suggestions.map((t) => (
                    <option key={t} value={t} />
                  ))}
                </datalist>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <span className="w-12 text-sm font-semibold">メモ</span>
                <div className="flex gap-1 text-sm">
                  {(["write", "preview"] as const).map((tab) => (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => setNoteTab(tab)}
                      className={`rounded px-2 py-0.5 ${
                        noteTab === tab ? "bg-zinc-200 dark:bg-zinc-700" : "text-zinc-500"
                      }`}
                    >
                      {tab === "write" ? "書く" : "プレビュー"}
                    </button>
                  ))}
                </div>
              </div>
              {noteTab === "write" ? (
                <textarea
                  value={draft.note}
                  onChange={(e) => setDraft({ ...draft, note: e.target.value })}
                  rows={10}
                  placeholder="Markdown で書けます。数式は $E=mc^2$ や $$...$$"
                  className="rounded border border-zinc-300 bg-transparent p-2 font-mono text-sm dark:border-zinc-700"
                />
              ) : (
                <div className="min-h-40 rounded border border-zinc-200 p-3 dark:border-zinc-800">
                  {draft.note.trim() ? (
                    <Markdown onChange={(note) => setDraft({ ...draft, note })}>
                      {draft.note}
                    </Markdown>
                  ) : (
                    <p className="text-sm text-zinc-500">（メモは空です）</p>
                  )}
                </div>
              )}
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelEdit}
                disabled={busy}
                className="rounded border border-zinc-300 px-4 py-1.5 disabled:opacity-50 dark:border-zinc-700"
              >
                キャンセル
              </button>
              <button
                type="button"
                onClick={save}
                disabled={busy}
                className="rounded bg-zinc-900 px-4 py-1.5 text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
              >
                {busy ? "保存中…" : "保存"}
              </button>
            </div>
          </section>
          {abstractSection}
        </>
      ) : (
        <>
          {paper.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {paper.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-zinc-100 px-2 py-0.5 text-sm dark:bg-zinc-800"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {abstractSection}

          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-bold">メモ</h2>
            {paper.note.trim() ? (
              // 保存中は押せないようにする（古いメモを元に書き換えてしまうのを防ぐ）
              <Markdown onChange={busy ? undefined : saveNote}>{paper.note}</Markdown>
            ) : (
              <p className="text-sm text-zinc-500">（メモはまだありません）</p>
            )}
          </section>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={startEdit}
              className="rounded bg-zinc-900 px-4 py-1.5 text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              編集
            </button>
            <button
              type="button"
              onClick={remove}
              disabled={busy}
              className="rounded border border-red-300 px-4 py-1.5 text-red-600 disabled:opacity-50 dark:border-red-800"
            >
              削除
            </button>
          </div>
        </>
      )}

    </main>
  );
}

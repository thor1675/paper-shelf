"use client";

import { useCallback, useEffect, useState } from "react";

import { BROWSER_API_URL, apiFetch, errorMessage } from "@/lib/api";

export type Status = {
  status: "queued" | "running" | "done" | "failed" | null;
  done: number;
  total: number;
  source_url: string | null;
  error: string | null;
};

// 訳文の表示。まだ訳していなければ「日本語に訳す」、訳している間は進み具合、終わったら訳文
export default function Reader({
  paperId,
  arxivUrl,
  initial,
}: {
  paperId: number;
  arxivUrl: string;
  // 最初の状態はサーバで取ってきて渡す
  initial: Status | null;
}) {
  const [status, setStatus] = useState<Status | null>(initial);
  const [error, setError] = useState<string | null>(null);
  // 訳し直したときに iframe を読み直させるための番号
  const [version, setVersion] = useState(0);

  const load = useCallback(async () => {
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/papers/${paperId}/translation`);
      if (!res.ok) return setError(await errorMessage(res));
      setStatus(await res.json());
    } catch {
      setError("backend に接続できませんでした");
    }
  }, [paperId]);

  // 訳している間だけ、2 秒ごとに進み具合を見に行く
  const working = status?.status === "queued" || status?.status === "running";
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [working, load]);

  async function start(force: boolean) {
    setError(null);
    try {
      const res = await apiFetch(`${BROWSER_API_URL}/papers/${paperId}/translation${force ? "?force=true" : ""}`, {
        method: "POST",
      });
      if (!res.ok) return setError(await errorMessage(res));
      setStatus(await res.json());
      setVersion((v) => v + 1);
    } catch {
      setError("backend に接続できませんでした");
    }
  }

  const button = "rounded bg-zinc-900 px-4 py-1.5 text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900";

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-zinc-500">
        arXiv の HTML 版を、この PC の翻訳モデル（FuguMT）で訳します。自分で読むためだけに使用し、公開や共有はしないでください
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}


      {status === null && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm text-red-600">翻訳の状態を取得できませんでした。backend が起動しているか確認してください</p>
          <button type="button" onClick={load} className={button}>
            もう一度読み込む
          </button>
        </div>
      )}

      {status?.status === null && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">論文 1 本につき 1 分ほどかかります。訳す場合は下の「日本語に翻訳」をクリック</p>
          <button type="button" onClick={() => start(false)} className={button}>
            日本語に翻訳
          </button>
        </div>
      )}

      {working && status && (
        <div className="flex flex-col gap-2" role="status">
          <p className="text-sm">
            {status.total ? `訳しています… ${status.done} / ${status.total} 段落` : "HTML 版を取得中…"}
          </p>
          <div className="h-2 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800">
            <div
              className="h-full bg-zinc-900 transition-all dark:bg-zinc-100"
              style={{ width: `${status.total ? (status.done / status.total) * 100 : 5}%` }}
            />
          </div>
        </div>
      )}

      {status?.status === "failed" && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm text-red-600">{status.error ?? "翻訳に失敗しました"}</p>
          <button type="button" onClick={() => start(true)} className={button}>
            もう一度訳す
          </button>
        </div>
      )}

      {status?.status === "done" && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <a href={status.source_url ?? arxivUrl} target="_blank" rel="noopener noreferrer" className="underline">
              原文を開く
            </a>
            <button type="button" onClick={() => start(true)} className="text-zinc-500 underline">
              訳し直す
            </button>
            <span className="text-xs text-zinc-500">段落の下の「原文」をクリックすると英語が出ます</span>
          </div>
          {/* 訳文は arXiv から取ってきた HTML なので、スクリプトを動かさない枠（sandbox）で表示する。
              リンクは新しいタブで開く */}
          <iframe
            key={version}
            src={`${BROWSER_API_URL}/papers/${paperId}/translation.html`}
            title="日本語訳"
            sandbox="allow-popups allow-popups-to-escape-sandbox"
            className="h-[80vh] w-full rounded border border-zinc-200 bg-white dark:border-zinc-800"
          />
        </>
      )}
    </div>
  );
}

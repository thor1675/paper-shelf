export const STATUSES = ["unread", "reading", "read"] as const;
export type Status = (typeof STATUSES)[number];

export type Paper = {
  id: number;
  arxiv_id: string;
  title: string;
  authors: string[];
  abstract: string;
  published: string;
  tags: string[];
  note: string;
  status: Status;
  created_at: string;
  arxiv_url: string;
  pdf_url: string;
};

export type TagCount = { name: string; count: number };

export const STATUS_LABELS: Record<Status, string> = {
  unread: "未読",
  reading: "読んでいる",
  read: "読んだ",
};

// Server Component はコンテナ内で動くので backend のサービス名で、
// ブラウザはホストから見た localhost で backend を呼ぶ
export const SERVER_API_URL = process.env.API_URL ?? "http://localhost:8000";
export const BROWSER_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// FastAPI のエラーは detail が文字列か、入力エラーの配列のどちらか
export async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((e: { msg: string }) => e.msg).join(" / ");
    }
  } catch {
    // JSON でない応答
  }
  return `エラーが発生しました（${res.status}）`;
}

// backend の normalize_tags と同じ規則（小文字・前後の空白除去・空文字と重複の除去）
export function addTag(tags: string[], raw: string): string[] {
  const t = raw.trim().toLowerCase();
  return t && !tags.includes(t) ? [...tags, t] : tags;
}

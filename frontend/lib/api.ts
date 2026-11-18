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
  read_at: string | null;
  openalex_id: string | null;
  // OpenAlex と同期するまでは null
  citation_count: number | null;
  arxiv_url: string;
  pdf_url: string;
};

export type TagCount = { name: string; count: number };

export const STATUS_LABELS: Record<Status, string> = {
  unread: "未読",
  reading: "精読中",
  read: "読了",
};

// Server Component はコンテナ内で動くので backend のサービス名で、
// ブラウザはホストから見た localhost で backend を呼ぶ
export const SERVER_API_URL = process.env.API_URL ?? "http://localhost:8000";
export const BROWSER_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ログインの Cookie の名前（backend の auth.py と同じ）
export const SESSION_COOKIE = "ps_session";

export type Me = { id: number; username: string; slack_linked: boolean };

// ブラウザから backend を呼ぶ。ログインの Cookie を一緒に送り、ログインが切れていたらログイン画面へ移る
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, { ...init, credentials: "include" });
  if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    // ログインし直したあとに画面全体（上のメニューの名前など）を読み直したいので、ページごと移る
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
  }
  return res;
}

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

// arXiv の検索結果や新着。登録済みなら paper_id が入る
export type SearchItem = {
  arxiv_id: string;
  title: string;
  authors: string[];
  abstract: string;
  published: string;
  paper_id: number | null;
  arxiv_url: string;
};

export type BatchItem = {
  input: string;
  arxiv_id: string | null;
  result: "created" | "exists" | "duplicate" | "invalid" | "not_found" | "unavailable" | "busy";
  paper_id: number | null;
  title: string | null;
};

export type Watch = {
  id: number;
  query: string;
  created_at: string;
  notified_at: string | null;
};

export function formatAuthors(authors: string[]) {
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")} 他${authors.length - 3}人`;
}

// --- 引用・被引用（OpenAlex） ---

export type CitationNode = {
  work_id: string;
  arxiv_id: string | null;
  title: string;
  year: number | null;
  authors: string[];
  cited_by_count: number;
  paper_id: number | null;
};

export type CitationMap = {
  center: CitationNode;
  references: CitationNode[];
  citations: CitationNode[];
  references_total: number;
  citations_total: number;
};

export type MissingItem = CitationNode & { cited_by_papers: number[] };

export type LibraryGraph = {
  nodes: { paper_id: number; title: string; label: string; year: number; cited_by_count: number | null }[];
  edges: { source: number; target: number }[];
  unsynced: number;
};

export type ReadStats = { months: { month: string; count: number }[]; unknown: number };

// 引用の図の URL。arXiv にある論文は arXiv の番号、無ければ OpenAlex の ID で開く
export function citationHref(n: { arxiv_id: string | null; work_id: string }) {
  return `/citations?key=${encodeURIComponent(n.arxiv_id ?? n.work_id)}`;
}

// 図の円などに付ける短い名前（Vaswani 2017）
export function shortLabel(n: { authors: string[]; year: number | null }) {
  const last = n.authors[0]?.split(" ").at(-1) ?? "?";
  return `${last} ${n.year ?? ""}`.trim();
}

export function formatCount(n: number) {
  return n >= 10000 ? `${Math.round(n / 1000)}k` : n.toLocaleString("ja-JP");
}

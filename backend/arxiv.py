import logging
import re
import threading
import time
from datetime import date

import feedparser
import httpx

ARXIV_API = "https://export.arxiv.org/api/query"
# arXiv API の利用規約で、リクエストは 3 秒に 1 回まで
ARXIV_INTERVAL = 3.0
# arXiv に繋がらなかったときに画面に出す文。原因（例外の名前など）はログにだけ出す
UNAVAILABLE_MESSAGE = "arXiv に繋がらないため登録できませんでした。しばらくしてからもう一度試してください"
SEARCH_UNAVAILABLE_MESSAGE = "arXiv に繋がらないため検索できませんでした。しばらくしてからもう一度試してください"
# arXiv に「問い合わせが多すぎる」（429）と断られたとき。押し直すと長引くので、待ってほしいと伝える
BUSY_MESSAGE = "arXiv が混んでいるため登録できませんでした。数分待ってから試してください"
SEARCH_BUSY_MESSAGE = "arXiv が混んでいるため検索できませんでした。数分待ってから試してください"
# 429（問い合わせが多すぎる）や 503 のとき、やり直す前に待つ秒数の上限
MAX_RETRY_WAIT = 10.0
# 応答を待つ秒数。ID で取るのはすぐ返るが、キーワード検索は arXiv 側で 10 秒以上かかることがある
FETCH_TIMEOUT = 10.0
SEARCH_TIMEOUT = 30.0
# 同じ検索の結果を覚えておく秒数。押し直しても arXiv に問い合わせない（問い合わせすぎると 429 で断られる）
SEARCH_CACHE_TTL = 600.0
_search_cache: dict[tuple, tuple[float, tuple[int, list[dict]]]] = {}

logger = logging.getLogger(__name__)

class PaperNotFound(Exception):
    """arXiv に該当する論文が無い"""

class ArxivUnavailable(Exception):
    """arXiv に繋がらない、またはおかしな応答が返ってきた"""

class ArxivBusy(ArxivUnavailable):
    """やり直しても arXiv に 429（問い合わせが多すぎる）で断られた"""

def normalize_arxiv_id(raw: str) -> str:
    """
    URLやバージョン番号を含むarXiv IDを正規化する
    例: https://arxiv.org/abs/2401.12345v2/ ・ arXiv:2401.12345 ・ ARXIV.ORG/html/2401.12345v1 → 2401.12345
    """
    s = raw.strip()
    m = re.search(r"(?i:arxiv\.org)/(?:abs|pdf|html)/([^\s?#]+)", s)
    if m:
        s = m.group(1)
    s = re.sub(r"(?i)^arxiv:\s*", "", s)
    s = re.sub(r"^(?:abs|pdf|html)/", "", s)
    s = s.rstrip("/").removesuffix(".pdf")
    s = re.sub(r"v\d+$", "", s)
    return s

def is_valid_arxiv_id(arxiv_id: str) -> bool:
    """
    新形式（2301.12345）と旧形式（hep-th/9901001）のどちらかに一致するか
    """
    return bool(
        re.fullmatch(r"\d{4}\.\d{4,5}", arxiv_id)
        or re.fullmatch(r"[a-z\-]+(\.[A-Z]{2})?/\d{7}", arxiv_id)
    )

# 画面と Slack から同時に登録されても、arXiv への問い合わせが 3 秒に 1 回を超えないようにする
_lock = threading.Lock()
_last_call = 0.0

def _retry_wait(res: httpx.Response) -> float:
    """Retry-After（秒）があればそれに従い、無ければ 5 秒。長すぎる指定は MAX_RETRY_WAIT で打ち切る"""
    try:
        return min(float(res.headers.get("Retry-After", 5)), MAX_RETRY_WAIT)
    except ValueError:
        return 5.0

def _get(params: dict, timeout: float = FETCH_TIMEOUT) -> httpx.Response:
    global _last_call
    with _lock:
        for attempt in range(2):
            wait = ARXIV_INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                res = httpx.get(ARXIV_API, params=params, timeout=timeout)
            finally:
                _last_call = time.monotonic()
            # 混んでいると言われたら、少し待って 1 回だけやり直す
            if res.status_code in (429, 503) and attempt == 0:
                logger.info("arXiv API が %s を返したのでやり直します", res.status_code)
                time.sleep(_retry_wait(res))
                continue
            return res
        return res

def _query(params: dict, what: str, timeout: float = FETCH_TIMEOUT) -> feedparser.FeedParserDict:
    """arXiv API に問い合わせて Atom を解析する。繋がらない・おかしな応答は ArxivUnavailable"""
    try:
        res = _get(params, timeout=timeout)
        if res.status_code == 429:
            logger.warning("arXiv API に断られました（429）%s", what)
            raise ArxivBusy(BUSY_MESSAGE)
        res.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("arXiv API に接続できませんでした %s: %r", what, e)
        raise ArxivUnavailable(UNAVAILABLE_MESSAGE) from e

    feed = feedparser.parse(res.text)
    # メンテナンス中などは 200 で HTML が返ってくる。Atom でなければ「見つからない」ではなく障害として扱う
    if not feed.version.startswith("atom"):
        logger.warning("arXiv API の応答が Atom ではありません %s: %.200s", what, res.text)
        raise ArxivUnavailable(UNAVAILABLE_MESSAGE)
    return feed

def _to_paper(entry) -> dict | None:
    """Atom のエントリを論文の dict にする。エラーのエントリなら None"""
    if entry.get("title", "").strip() == "Error" or "id" not in entry:
        return None
    try:
        return {
            # entry.id は http://arxiv.org/abs/1706.03762v7 の形
            "arxiv_id": normalize_arxiv_id(entry.id),
            "title": " ".join(entry.title.split()),
            "authors": [a.name for a in entry.get("authors", [])],
            "abstract": " ".join(entry.summary.split()),
            "published": date.fromisoformat(entry.published[:10]),
        }
    except (AttributeError, KeyError, ValueError) as e:
        logger.warning("arXiv API の応答に必要な項目がありません %s: %r", entry.get("id"), e)
        raise ArxivUnavailable(UNAVAILABLE_MESSAGE) from e

# まとめて問い合わせる上限。arXiv の 1 回の応答として無理のない数にする
MAX_BATCH = 50

def fetch_papers(arxiv_ids: list[str]) -> dict[str, dict]:
    """
    複数の論文を 1 回の問い合わせでまとめて取る。arXiv に無い ID は結果に入らない
    （arXiv は存在しない ID をエラーにせず、黙って結果から外す）
    """
    if not arxiv_ids:
        return {}
    feed = _query({"id_list": ",".join(arxiv_ids), "max_results": len(arxiv_ids)}, ",".join(arxiv_ids))
    papers = (_to_paper(e) for e in feed.entries)
    return {p["arxiv_id"]: p for p in papers if p and p["arxiv_id"] in arxiv_ids}

def fetch_paper(arxiv_id: str) -> dict:
    """
    arXiv APIを使って論文情報を取得する
    """
    paper = fetch_papers([arxiv_id]).get(arxiv_id)
    if paper is None:
        raise PaperNotFound(f"arXiv ID: {arxiv_id}はarXivにありませんでした")
    return paper

def build_search_query(q: str) -> str:
    """
    画面の検索語を arXiv の search_query にする。
    ti:（タイトル）au:（著者）abs: cat: などを含めばそのまま使い、
    普通の単語なら全項目からの AND 検索にする（"..." で囲めば語句のまま）
    """
    q = q.strip()
    if re.search(r"\b(?:ti|au|abs|cat|all|co|jr|rn|id):", q):
        return q
    terms = re.findall(r'"[^"]+"|\S+', q)
    return " AND ".join(f"all:{t}" for t in terms)

def search_arxiv(q: str, start: int = 0, max_results: int = 20, newest: bool = False) -> tuple[int, list[dict]]:
    """arXiv を検索して（総件数, 論文の list）を返す。newest なら投稿の新しい順"""
    params = {
        "search_query": build_search_query(q),
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate" if newest else "relevance",
        "sortOrder": "descending",
    }
    key = tuple(sorted(params.items()))
    hit = _search_cache.get(key)
    if hit and time.monotonic() - hit[0] < SEARCH_CACHE_TTL:
        return hit[1]
    feed = _query(params, q, timeout=SEARCH_TIMEOUT)
    total = int(feed.feed.get("opensearch_totalresults", 0) or 0)
    result = (total, [p for p in (_to_paper(e) for e in feed.entries) if p])
    # 古いものを捨ててから覚える（検索のたびに増え続けないように）
    now = time.monotonic()
    for k in [k for k, (t, _) in _search_cache.items() if now - t >= SEARCH_CACHE_TTL]:
        del _search_cache[k]
    _search_cache[key] = (now, result)
    return result

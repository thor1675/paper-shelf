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

logger = logging.getLogger(__name__)

class PaperNotFound(Exception):
    """arXiv に該当する論文が無い"""

class ArxivUnavailable(Exception):
    """arXiv に繋がらない、またはおかしな応答が返ってきた"""

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

def _get(params: dict) -> httpx.Response:
    global _last_call
    with _lock:
        wait = ARXIV_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            return httpx.get(ARXIV_API, params=params, timeout=10)
        finally:
            _last_call = time.monotonic()

def fetch_paper(arxiv_id: str) -> dict:
    """
    arXiv APIを使って論文情報を取得する
    """
    try:
        res = _get({"id_list": arxiv_id, "max_results": 1})
        res.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("arXiv API に接続できませんでした %s: %r", arxiv_id, e)
        raise ArxivUnavailable(UNAVAILABLE_MESSAGE) from e

    feed = feedparser.parse(res.text)
    # メンテナンス中などは 200 で HTML が返ってくる。Atom でなければ「見つからない」ではなく障害として扱う
    if not feed.version.startswith("atom"):
        logger.warning("arXiv API の応答が Atom ではありません %s: %.200s", arxiv_id, res.text)
        raise ArxivUnavailable(UNAVAILABLE_MESSAGE)

    not_found = PaperNotFound(f"arXiv ID: {arxiv_id}はarXivにありませんでした")
    if not feed.entries:
        raise not_found
    entry = feed.entries[0]
    if entry.get("title", "").strip() == "Error":
        raise not_found

    try:
        return {
            "arxiv_id": arxiv_id,
            "title": " ".join(entry.title.split()),
            "authors": [a.name for a in entry.get("authors", [])],
            "abstract": " ".join(entry.summary.split()),
            "published": date.fromisoformat(entry.published[:10]),
        }
    except (AttributeError, KeyError, ValueError) as e:
        logger.warning("arXiv API の応答に必要な項目がありません %s: %r", arxiv_id, e)
        raise ArxivUnavailable(UNAVAILABLE_MESSAGE) from e

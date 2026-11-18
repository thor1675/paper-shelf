"""
OpenAlex（論文の引用関係を無料で公開している API）とのやり取り。
Semantic Scholar はキー無しだと 429 が続いて使えなかったので、OpenAlex にした
"""

import html
import logging
import os
import re
import threading
import time

import httpx

from arxiv import is_valid_arxiv_id, normalize_arxiv_id

OPENALEX_API = "https://api.openalex.org"
# 連絡先を付けると OpenAlex の「丁寧な利用者」の枠に入り、混んでいても応答が速い（任意）
MAILTO = os.environ.get("OPENALEX_MAILTO", "")
# OpenAlex は 1 秒に 10 回まで。余裕を持たせる
INTERVAL = 0.2
# まとめて引くときの 1 回の件数。OpenAlex の filter で OR できる上限（100）より少なめ
CHUNK = 50
UNAVAILABLE_MESSAGE = "引用の情報を取得できませんでした。しばらくしてからもう一度試してください"

# 1 件ごとに取る項目（必要なものだけにして応答を小さくする）
NODE_FIELDS = "id,doi,title,publication_year,cited_by_count,authorships,locations"
WORK_FIELDS = NODE_FIELDS + ",referenced_works,related_works"

logger = logging.getLogger(__name__)


class ScholarUnavailable(Exception):
    """OpenAlex に繋がらない、またはおかしな応答"""


class WorkNotFound(Exception):
    """OpenAlex にその論文が無い"""


_lock = threading.Lock()
_last_call = 0.0


def _get(path: str, params: dict) -> dict:
    global _last_call
    params = {**params, **({"mailto": MAILTO} if MAILTO else {})}
    with _lock:
        for attempt in range(2):
            wait = INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                res = httpx.get(OPENALEX_API + path, params=params, timeout=30)
            except httpx.HTTPError as e:
                logger.warning("OpenAlex に接続できませんでした %s: %r", path, e)
                raise ScholarUnavailable(UNAVAILABLE_MESSAGE) from e
            finally:
                _last_call = time.monotonic()
            if res.status_code in (429, 503) and attempt == 0:
                time.sleep(2)
                continue
            if res.status_code == 404:
                raise WorkNotFound(path)
            if res.status_code != 200:
                logger.warning("OpenAlex が %s を返しました %s: %.200s", res.status_code, path, res.text)
                raise ScholarUnavailable(UNAVAILABLE_MESSAGE)
            try:
                return res.json()
            except ValueError as e:
                raise ScholarUnavailable(UNAVAILABLE_MESSAGE) from e
    raise ScholarUnavailable(UNAVAILABLE_MESSAGE)


def short_id(url_or_id: str) -> str:
    """https://openalex.org/W2626778328 → W2626778328"""
    return url_or_id.rsplit("/", 1)[-1]


def arxiv_id_of(work: dict) -> str | None:
    """
    OpenAlex の論文から arXiv の番号を取り出す。学会版とまとめられた論文は DOI が学会のものになるので、
    DOI（10.48550/arxiv.…）に無ければ掲載先の URL（arxiv.org/abs/…）を見る
    """
    candidates = [work.get("doi") or ""]
    for loc in work.get("locations") or []:
        candidates += [loc.get("landing_page_url") or "", loc.get("pdf_url") or ""]
    for c in candidates:
        m = re.search(r"10\.48550/arxiv\.(.+)$", c, re.I) or re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", c, re.I)
        if m:
            arxiv_id = normalize_arxiv_id(m.group(1))
            # DOI は小文字になっているので、旧形式（math.GT/…）は大文字に戻せないことがある
            if is_valid_arxiv_id(arxiv_id):
                return arxiv_id
    return None


def to_node(work: dict) -> dict:
    """画面に出す 1 本分。タイトルに入っていることがある <i> などのタグは外す"""
    authors = [a["author"]["display_name"] for a in work.get("authorships") or [] if a.get("author")]
    return {
        "work_id": short_id(work["id"]),
        "arxiv_id": arxiv_id_of(work),
        "title": html.unescape(re.sub(r"<[^>]+>", "", work.get("title") or "（タイトル不明）")),
        "year": work.get("publication_year"),
        "authors": authors,
        "cited_by_count": work.get("cited_by_count") or 0,
    }


def _arxiv_doi(arxiv_id: str) -> str:
    # arXiv の論文にはすべて 10.48550/arXiv.番号 の DOI が振られている
    return f"10.48550/arxiv.{arxiv_id.lower()}"


def works_by_arxiv(arxiv_ids: list[str], fields: str = WORK_FIELDS) -> dict[str, dict]:
    """arXiv の番号でまとめて引く。OpenAlex に無いものは結果に入らない"""
    found: dict[str, dict] = {}
    wanted = {i.lower(): i for i in arxiv_ids}
    for start in range(0, len(arxiv_ids), CHUNK):
        chunk = arxiv_ids[start : start + CHUNK]
        data = _get(
            "/works",
            {"filter": "doi:" + "|".join(_arxiv_doi(i) for i in chunk), "select": fields, "per-page": CHUNK},
        )
        for w in data.get("results", []):
            aid = arxiv_id_of(w)
            if aid and aid.lower() in wanted:
                found[wanted[aid.lower()]] = w
    return found


def works_by_ids(work_ids: list[str], fields: str = NODE_FIELDS) -> dict[str, dict]:
    """OpenAlex の ID（W…）でまとめて引く"""
    found: dict[str, dict] = {}
    ids = list(dict.fromkeys(work_ids))
    for start in range(0, len(ids), CHUNK):
        chunk = ids[start : start + CHUNK]
        data = _get("/works", {"filter": "openalex_id:" + "|".join(chunk), "select": fields, "per-page": CHUNK})
        for w in data.get("results", []):
            found[short_id(w["id"])] = w
    return found


def work(key: str) -> dict:
    """1 本を引く。key は arXiv の番号か OpenAlex の ID（W…）"""
    if re.fullmatch(r"W\d+", key):
        return _get(f"/works/{key}", {"select": WORK_FIELDS})
    return _get(f"/works/doi:{_arxiv_doi(key)}", {"select": WORK_FIELDS})


def citing_works(work_id: str, n: int = 30) -> tuple[int, list[dict]]:
    """この論文を引用している論文のうち、被引用数の多い n 本と、全体の本数"""
    data = _get(
        "/works",
        {"filter": f"cites:{work_id}", "sort": "cited_by_count:desc", "select": NODE_FIELDS, "per-page": n},
    )
    return data.get("meta", {}).get("count", 0), data.get("results", [])

import re
from datetime import date

import feedparser
import httpx

ARXIV_API = "https://export.arxiv.org/api/query"

def normalize_arxiv_id(raw: str) -> str:
    """
    URLやバージョン番号を含むarXiv IDを正規化する
    """
    s = raw.strip()
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", s)
    if m:
        s = m.group(1)
    s = s.removesuffix(".pdf")
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

def fetch_paper(arxiv_id: str) -> dict:
    """
    arXiv APIを使って論文情報を取得する
    """
    res = httpx.get(ARXIV_API, params={"id_list": arxiv_id, "max_results": 1}, timeout=10)
    res.raise_for_status()

    feed = feedparser.parse(res.text)
    if not feed.entries:
        raise ValueError(f"このarXiv ID: {arxiv_id}に該当する論文が見つかりませんでした。")

    entry = feed.entries[0]
    if entry.title.strip() == "Error":
        raise ValueError(f"このarXiv ID: {arxiv_id}に該当する論文が見つかりませんでした。")

    return {
        "arxiv_id": arxiv_id,
        "title": " ".join(entry.title.split()),
        "authors": [a.name for a in entry.authors],
        "abstract": " ".join(entry.summary.split()),
        "published": date.fromisoformat(entry.published[:10]),
    }

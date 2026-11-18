"""
arXiv の HTML 版を取ってきて、構造（見出し・数式・図・表・参考文献）を保ったまま本文を日本語に訳す。
訳すのは translator コンテナ（FuguMT）。訳文は自分で読むためだけに使い、公開・共有しない
"""

import html
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from sqlmodel import Session

from models import Translation

TRANSLATOR_URL = os.environ.get("TRANSLATOR_URL", "http://translator:8001")
# 1 回に translator へ送る段落の数
BATCH = 20
# 進み具合が更新されないまま、これだけたった翻訳は止まったものとみなす（backend の再起動など）
STALE_AFTER = timedelta(minutes=10)

# 段落の中で訳さずにそのまま残すもの（数式・引用・参照・脚注など）。目印に置き換えて訳し、あとで戻す
ATOMIC_TAGS = {"math", "cite", "a", "sup", "sub", "code", "img", "svg", "br"}
ATOMIC_CLASSES = {"ltx_note", "ltx_ref", "ltx_ERROR", "ltx_Math"}
# 訳す範囲から外すところ（参考文献・著者・表の中身・コード）
SKIP_CLASSES = {"ltx_bibliography", "ltx_authors", "ltx_listing", "ltx_tabular", "ltx_page_footer", "ltx_page_navbar"}
# 目印。FuguMT は XMATH1 や XREF2 のような語をそのまま書き写す（⟦1⟧ のような記号は消えてしまった）。
# ときどき "XREF 3" のように空白を入れて書き写すので、空白があっても戻す
MARK = re.compile(r"X\s?(MATH|REF)\s?(\d+)")

logger = logging.getLogger(__name__)


class NoHtml(Exception):
    """arXiv にも ar5iv にも HTML 版が無い"""


def fetch_html(arxiv_id: str) -> tuple[str, str]:
    """
    HTML 版を取る。新しい論文は arxiv.org/html、2023 年以前の多くは ar5iv（arXiv 公式の HTML 化）にある。
    （本文, 最終的な URL）を返す
    """
    for base in ("https://arxiv.org/html/", "https://ar5iv.labs.arxiv.org/html/"):
        try:
            res = httpx.get(base + arxiv_id, timeout=60, follow_redirects=True)
        except httpx.HTTPError as e:
            logger.warning("HTML 版を取得できませんでした %s: %r", base + arxiv_id, e)
            continue
        # ar5iv は変換できなかった論文でも 200 で別のページを返すので、本文の印（ltx_document）で見分ける
        if res.status_code == 200 and "ltx_document" in res.text:
            return res.text, str(res.url)
    raise NoHtml(arxiv_id)


def _classes(tag: Tag) -> set[str]:
    return set(tag.get("class") or [])


def _skipped(tag: Tag) -> bool:
    return any(_classes(p) & SKIP_CLASSES or p.name in ("table", "pre", "nav") for p in [tag, *tag.parents] if isinstance(p, Tag))


def flatten(node: Tag) -> tuple[str, list[str]]:
    """
    段落を「訳す文」と「目印で置き換えた要素の HTML」に分ける。
    斜体などの飾りは文だけ残し（訳すと位置が変わるため）、数式などは XMATH1 / XREF2 の目印にする
    """
    parts: list[str] = []
    kept: list[str] = []

    def walk(n: Tag) -> None:
        for child in n.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name in ATOMIC_TAGS or _classes(child) & ATOMIC_CLASSES:
                    kind = "MATH" if child.name == "math" or "ltx_Math" in _classes(child) else "REF"
                    kept.append(str(child))
                    parts.append(f" X{kind}{len(kept)} ")
                else:
                    walk(child)

    walk(node)
    return " ".join("".join(parts).split()), kept


def restore(translated: str, kept: list[str]) -> str:
    """訳文の目印を元の要素に戻す。訳文から消えた目印の要素は、なくならないよう最後に付け足す"""
    used: set[int] = set()

    def put(m: re.Match) -> str:
        i = int(m.group(2))
        if 1 <= i <= len(kept) and i not in used:
            used.add(i)
            return kept[i - 1]
        return ""

    out = MARK.sub(put, html.escape(translated, quote=False))
    missing = [k for i, k in enumerate(kept, 1) if i not in used]
    return out + ("（" + " ".join(missing) + "）" if missing else "")


def prepare(raw: str, url: str) -> tuple[BeautifulSoup, list[Tag]]:
    """HTML を安全にして（スクリプトを除き、URL を絶対にする）、訳す段落の一覧を返す"""
    soup = BeautifulSoup(raw, "html.parser")
    # 図の一部（SVG）は <object data="…svg"> で埋め込まれている。<object> は中でスクリプトが動きうるので、
    # スクリプトの動かない <img> に置き換えて図を残す。それ以外の <object> は消す
    for t in soup("object"):
        data = t.get("data")
        if isinstance(data, str) and t.get("type") == "image/svg+xml":
            img = soup.new_tag("img", src=data, alt="図")
            for attr in ("id", "class", "style", "width", "height"):
                if t.get(attr):
                    img[attr] = t[attr]
            t.replace_with(img)
        else:
            t.decompose()
    for t in soup(["script", "iframe", "embed", "base"]):
        t.decompose()
    for t in soup.find_all(True):
        for attr in list(t.attrs):
            if attr.lower().startswith("on"):  # onclick などのスクリプト
                del t[attr]
        # 画像や CSS は arXiv から読むので絶対 URL にする。ページ内のリンク（#S1）はそのまま
        for attr in ("src", "href"):
            v = t.get(attr)
            if isinstance(v, str) and v and not v.startswith("#"):
                if v.strip().lower().startswith("javascript:"):
                    del t[attr]
                else:
                    t[attr] = urljoin(url, v)
        if t.name == "a" and not str(t.get("href", "")).startswith("#"):
            t["target"] = "_blank"
            t["rel"] = "noopener noreferrer"
    blocks = [
        t
        for t in soup.find_all(["p", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6"])
        if not _skipped(t)
        # 見出しの中の p など、外側で訳すものの内側は数えない
        and not any(p.name in ("p", "figcaption") for p in t.parents)
        and re.search(r"[A-Za-z]{2}", t.get_text())
    ]
    return soup, blocks


def finish(soup: BeautifulSoup, url: str) -> str:
    """訳した HTML の先頭に、機械翻訳であることと原文へのリンクを付ける"""
    head = soup.head or soup.new_tag("head")
    if soup.head is None and soup.html:
        soup.html.insert(0, head)
    style = soup.new_tag("style")
    style.string = """
      .ps-banner { font: 14px/1.6 system-ui, sans-serif; background: #eef4f3; color: #16201f; border: 1px solid #c9dad7;
                   border-radius: 6px; padding: 8px 12px; margin: 12px auto; max-width: 52rem; }
      .ps-banner a { color: #1d6b66; }
      details.ps-orig { margin: 4px 0 10px; font-size: 0.86em; color: #555; }
      details.ps-orig > summary { cursor: pointer; color: #1d6b66; font-size: 0.85em; }
      @media (prefers-color-scheme: dark) { .ps-banner { background: #182120; color: #e7eceb; border-color: #2a3634; }
                                            .ps-banner a, details.ps-orig > summary { color: #6cc2ba; } details.ps-orig { color: #aaa; } }
    """
    head.append(style)
    banner = BeautifulSoup(
        '<div class="ps-banner">PAPER - Shelf が FuguMT で機械翻訳した訳文です。自分で読むためだけに使用し、公開や共有はしないでください。'
        f'「▶原文」より原文を確認できます。<a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">原文を arXiv で開く</a></div>',
        "html.parser",
    )
    (soup.body or soup).insert(0, banner)
    return str(soup)


def translate_texts(texts: list[str]) -> list[str]:
    res = httpx.post(f"{TRANSLATOR_URL}/translate", json={"texts": texts}, timeout=600)
    res.raise_for_status()
    return res.json()["texts"]


def run(session: Session, arxiv_id: str) -> None:
    """1 本を訳して translations 表に書き込む。進み具合は BATCH 段落ごとに記録する"""
    t = session.get(Translation, arxiv_id)
    try:
        raw, url = fetch_html(arxiv_id)
        soup, blocks = prepare(raw, url)
        t.status, t.done, t.total, t.source_url = "running", 0, len(blocks), url
        _save(session, t)
        for start in range(0, len(blocks), BATCH):
            chunk = blocks[start : start + BATCH]
            flat = [flatten(b) for b in chunk]
            ja = translate_texts([text for text, _ in flat])
            for block, (text, kept), translated in zip(chunk, flat, ja):
                original = block.decode_contents()
                block.clear()
                block.append(BeautifulSoup(restore(translated, kept), "html.parser"))
                if block.name.startswith("h"):
                    # 見出しは原文を、触れたときに出す（目印の入っていない元の文）
                    block["title"] = " ".join(BeautifulSoup(original, "html.parser").get_text().split())
                else:
                    orig = BeautifulSoup(f'<details class="ps-orig"><summary>原文</summary>{original}</details>', "html.parser")
                    block.insert_after(orig)
            t.done = start + len(chunk)
            _save(session, t)
        t.html, t.status, t.error = finish(soup, url), "done", None
    except NoHtml:
        t.status, t.error = "failed", "この論文には HTML 版がありません（arXiv にも ar5iv にもありませんでした）"
    except httpx.HTTPError as e:
        logger.warning("翻訳に失敗しました %s: %r", arxiv_id, e)
        t.status, t.error = "failed", "翻訳の途中で失敗しました。translator が起動しているか確認して、もう一度試してください"
    _save(session, t)


def _save(session: Session, t: Translation) -> None:
    t.updated_at = datetime.now(timezone.utc)
    session.add(t)
    session.commit()


def is_stale(t: Translation) -> bool:
    return t.status in ("queued", "running") and t.updated_at < datetime.now(timezone.utc) - STALE_AFTER

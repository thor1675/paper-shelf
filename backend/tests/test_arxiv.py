import httpx
import pytest

import arxiv
from arxiv import ArxivUnavailable, PaperNotFound, fetch_paper, is_valid_arxiv_id, normalize_arxiv_id


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1706.03762", "1706.03762"),
        ("  1706.03762v7 ", "1706.03762"),
        ("https://arxiv.org/abs/1706.03762v5", "1706.03762"),
        ("https://arxiv.org/pdf/1706.03762v7.pdf", "1706.03762"),
        ("https://arxiv.org/abs/2401.12345/", "2401.12345"),
        ("https://arxiv.org/pdf/2401.12345v2/", "2401.12345"),
        ("https://arxiv.org/html/2401.12345v1", "2401.12345"),
        ("https://arxiv.org/abs/2401.12345?context=cs", "2401.12345"),
        ("HTTPS://ARXIV.ORG/abs/2401.12345", "2401.12345"),
        ("arXiv:2401.12345", "2401.12345"),
        ("ARXIV: 2401.12345v3", "2401.12345"),
        ("abs/2401.12345v2", "2401.12345"),
        ("https://arxiv.org/abs/hep-th/9901001v2", "hep-th/9901001"),
    ],
)
def test_normalize_arxiv_id(raw, expected):
    assert normalize_arxiv_id(raw) == expected
    assert is_valid_arxiv_id(normalize_arxiv_id(raw))


@pytest.mark.parametrize(
    "arxiv_id, valid",
    [
        ("1706.03762", True),
        ("2401.1234", True),  # 2014 年以前の 4 桁
        ("math.GT/0309136", True),
        ("hello", False),
        ("2401.123456", False),
        ("1706.03762v2", False),  # バージョンは正規化で外してから判定する
        ("", False),
    ],
)
def test_is_valid_arxiv_id(arxiv_id, valid):
    assert is_valid_arxiv_id(arxiv_id) is valid


ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">{entry}</feed>"""

ENTRY = """<entry>
  <title>Attention Is
    All You Need</title>
  <summary>  The dominant
  sequence models.  </summary>
  <published>2017-06-12T17:57:34Z</published>
  <author><name>Ashish Vaswani</name></author>
  <author><name>Noam Shazeer</name></author>
</entry>"""


@pytest.fixture
def fake_arxiv(monkeypatch):
    """arxiv._get を差し替えて、返す本文とステータスを決められるようにする"""
    monkeypatch.setattr(arxiv, "ARXIV_INTERVAL", 0)

    def respond(text: str = "", status: int = 200, exc: Exception | None = None):
        def _get(params):
            if exc:
                raise exc
            return httpx.Response(status, text=text, request=httpx.Request("GET", arxiv.ARXIV_API))

        monkeypatch.setattr(arxiv, "_get", _get)

    return respond


def test_fetch_paper_parses_entry(fake_arxiv):
    fake_arxiv(ATOM.format(entry=ENTRY))
    p = fetch_paper("1706.03762")
    # 改行や連続した空白は 1 つにまとめる
    assert p["title"] == "Attention Is All You Need"
    assert p["abstract"] == "The dominant sequence models."
    assert p["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert str(p["published"]) == "2017-06-12"


def test_fetch_paper_not_found(fake_arxiv):
    fake_arxiv(ATOM.format(entry=""))
    with pytest.raises(PaperNotFound):
        fetch_paper("9999.99999")


def test_fetch_paper_error_entry_is_not_found(fake_arxiv):
    # 存在しない ID でも、arXiv はエラーではなくタイトルが Error のエントリを返す
    fake_arxiv(ATOM.format(entry="<entry><title>Error</title><summary>incorrect id</summary></entry>"))
    with pytest.raises(PaperNotFound):
        fetch_paper("9999.99999")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"exc": httpx.ConnectError("down")},
        {"status": 503, "text": "Service Unavailable"},
        {"status": 429, "text": "Too Many Requests"},
        # メンテナンス中は 200 で HTML が返ってくる。「見つからない」にしてはいけない
        {"text": "<html><body>arXiv is under maintenance</body></html>"},
        # 必要な項目が欠けたエントリ
        {"text": ATOM.format(entry="<entry><title>Something</title></entry>")},
    ],
)
def test_fetch_paper_unavailable(fake_arxiv, kwargs):
    fake_arxiv(**kwargs)
    with pytest.raises(ArxivUnavailable):
        fetch_paper("1706.03762")


def test_requests_are_spaced(monkeypatch):
    # 続けて呼んでも、arXiv への問い合わせの間隔は ARXIV_INTERVAL 以上空く
    calls: list[float] = []
    monkeypatch.setattr(arxiv, "ARXIV_INTERVAL", 0.2)
    monkeypatch.setattr(arxiv, "_last_call", 0.0)
    monkeypatch.setattr(
        arxiv.httpx,
        "get",
        lambda *a, **k: calls.append(arxiv.time.monotonic())
        or httpx.Response(200, text="", request=httpx.Request("GET", arxiv.ARXIV_API)),
    )
    for _ in range(3):
        arxiv._get({})
    assert all(b - a >= 0.19 for a, b in zip(calls, calls[1:]))

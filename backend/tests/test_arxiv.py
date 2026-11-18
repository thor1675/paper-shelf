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
  <id>http://arxiv.org/abs/1706.03762v7</id>
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
    monkeypatch.setattr(arxiv, "_search_cache", {})

    def respond(text: str = "", status: int = 200, exc: Exception | None = None):
        def _get(params, timeout=None):
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
        {"text": ATOM.format(entry="<entry><id>http://arxiv.org/abs/1706.03762v1</id><title>Something</title></entry>")},
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


def entry(arxiv_id: str, title: str, published: str = "2024-01-02") -> str:
    return f"""<entry><id>http://arxiv.org/abs/{arxiv_id}v1</id><title>{title}</title>
<summary>s</summary><published>{published}T00:00:00Z</published><author><name>A</name></author></entry>"""


def test_fetch_papers_returns_found_only(fake_arxiv):
    # arXiv は存在しない ID を黙って結果から外す
    fake_arxiv(ATOM.format(entry=entry("2401.00001", "One") + entry("hep-th/9901001", "Old")))
    got = arxiv.fetch_papers(["2401.00001", "9999.99999", "hep-th/9901001"])
    assert set(got) == {"2401.00001", "hep-th/9901001"}
    assert got["hep-th/9901001"]["title"] == "Old"


def test_fetch_papers_empty_list_does_not_call_arxiv(monkeypatch):
    monkeypatch.setattr(arxiv, "_get", lambda params, timeout=None: pytest.fail("呼ばれてはいけない"))
    assert arxiv.fetch_papers([]) == {}


@pytest.mark.parametrize(
    "q, expected",
    [
        ("dense retrieval", "all:dense AND all:retrieval"),
        ('"query rewriting" japanese', 'all:"query rewriting" AND all:japanese'),
        ("ti:attention AND au:vaswani", "ti:attention AND au:vaswani"),
    ],
)
def test_build_search_query(q, expected):
    assert arxiv.build_search_query(q) == expected


def test_search_arxiv(fake_arxiv):
    feed = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<opensearch:totalResults>42</opensearch:totalResults>{e}</feed>""".format(e=entry("2401.00001", "One") + entry("2401.00002", "Two"))
    fake_arxiv(feed)
    total, papers = arxiv.search_arxiv("dense retrieval")
    assert total == 42
    assert [p["arxiv_id"] for p in papers] == ["2401.00001", "2401.00002"]


def test_retries_once_on_429(monkeypatch):
    # 429 が返ったら Retry-After だけ待って 1 回やり直す。2 回目も駄目ならそのまま返す
    calls, sleeps = [], []
    responses = [
        httpx.Response(429, headers={"Retry-After": "2"}, request=httpx.Request("GET", arxiv.ARXIV_API)),
        httpx.Response(200, text="ok", request=httpx.Request("GET", arxiv.ARXIV_API)),
    ]
    monkeypatch.setattr(arxiv, "ARXIV_INTERVAL", 0)
    monkeypatch.setattr(arxiv.time, "sleep", sleeps.append)
    monkeypatch.setattr(arxiv.httpx, "get", lambda *a, **k: calls.append(1) or responses[len(calls) - 1])
    assert arxiv._get({}).status_code == 200
    assert len(calls) == 2 and 2.0 in sleeps


def test_retry_wait_is_capped():
    req = httpx.Request("GET", arxiv.ARXIV_API)
    assert arxiv._retry_wait(httpx.Response(429, headers={"Retry-After": "3600"}, request=req)) == arxiv.MAX_RETRY_WAIT
    assert arxiv._retry_wait(httpx.Response(429, request=req)) == 5.0
    assert arxiv._retry_wait(httpx.Response(429, headers={"Retry-After": "soon"}, request=req)) == 5.0


def test_search_is_cached_and_uses_longer_timeout(monkeypatch):
    # 同じ検索を続けても arXiv に問い合わせるのは 1 回だけ。検索は待ち時間を長くとる
    calls = []
    feed = '<feed xmlns="http://www.w3.org/2005/Atom">' + entry("2401.00001", "One") + "</feed>"
    monkeypatch.setattr(arxiv, "_search_cache", {})
    monkeypatch.setattr(
        arxiv, "_get",
        lambda params, timeout=None: calls.append(timeout)
        or httpx.Response(200, text=feed, request=httpx.Request("GET", arxiv.ARXIV_API)),
    )
    a = arxiv.search_arxiv("dense retrieval")
    b = arxiv.search_arxiv("dense retrieval")
    assert a == b and calls == [arxiv.SEARCH_TIMEOUT]
    arxiv.search_arxiv("dense retrieval", newest=True)
    assert len(calls) == 2


def test_failed_search_is_not_cached(monkeypatch):
    calls = []

    def _get(params, timeout=None):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(arxiv, "_search_cache", {})
    monkeypatch.setattr(arxiv, "_get", _get)
    for _ in range(2):
        with pytest.raises(ArxivUnavailable):
            arxiv.search_arxiv("dense retrieval")
    assert len(calls) == 2


def test_429_after_retry_is_busy(fake_arxiv):
    # やり直しても 429 なら「混んでいる」。繋がらないとき（ArxivUnavailable）の一種として扱える
    fake_arxiv(status=429)
    with pytest.raises(arxiv.ArxivBusy) as e:
        fetch_paper("1706.03762")
    assert isinstance(e.value, ArxivUnavailable)
    assert str(e.value) == arxiv.BUSY_MESSAGE

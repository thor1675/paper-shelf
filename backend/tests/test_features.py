"""まとめて登録・BibTeX・arXiv 検索・新着の通知"""

import pytest

import conftest
from bibtex import cite_key, to_bibtex
from test_api import add


# --- まとめて登録 ---


def test_batch_reports_each_line(client):
    add(client, "1706.03762")
    res = client.post("/papers/batch", json={"items": [
        "https://arxiv.org/abs/1810.04805v2",  # 新しく登録
        "arXiv:1706.03762",                     # 登録済み
        "1810.04805",                           # 同じものが 2 回
        "hello",                                # 形式違い
        "9999.99999",                           # arXiv に無い
        "hep-th/9901001",                       # 旧形式も新しく登録
    ]})
    assert res.status_code == 200
    got = [(i["input"], i["arxiv_id"], i["result"]) for i in res.json()]
    assert got == [
        ("https://arxiv.org/abs/1810.04805v2", "1810.04805", "created"),
        ("arXiv:1706.03762", "1706.03762", "exists"),
        ("1810.04805", "1810.04805", "duplicate"),
        ("hello", None, "invalid"),
        ("9999.99999", "9999.99999", "not_found"),
        ("hep-th/9901001", "hep-th/9901001", "created"),
    ]
    assert res.json()[0]["title"].startswith("BERT")
    assert len(client.get("/papers").json()) == 3


def test_batch_when_arxiv_is_down(client):
    res = client.post("/papers/batch", json={"items": ["1706.03762", "2401.00502"]})
    assert [i["result"] for i in res.json()] == ["unavailable", "unavailable"]
    assert client.get("/papers").json() == []


@pytest.mark.parametrize("body", [{"items": []}, {"items": ["1706.03762"] * 51}])
def test_batch_size_limits(client, body):
    assert client.post("/papers/batch", json=body).status_code == 422


# --- BibTeX ---


@pytest.mark.parametrize(
    "authors, year, title, key",
    [
        (["Ashish Vaswani", "Noam Shazeer"], 2017, "Attention Is All You Need", "vaswani2017attention"),
        (["Hinrich Schütze"], 2020, "On the Theory of Things", "schutze2020theory"),
        (["Jacob Devlin"], 2018, "BERT: Pre-training of Deep Bidirectional Transformers", "devlin2018bert"),
        ([], 2024, "The Unknown", "anon2024unknown"),
    ],
)
def test_cite_key(authors, year, title, key):
    assert cite_key(authors, year, title) == key


def test_export_bib_follows_filters(client):
    add(client, "1706.03762", tags=["nlp"])
    add(client, "1810.04805", tags=["nlp"])
    add(client, "2005.14165")
    res = client.get("/papers/export.bib?tag=nlp&sort=published&order=asc")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-bibtex")
    assert 'filename="paper-shelf.bib"' in res.headers["content-disposition"]
    body = res.text
    assert body.index("@article{vaswani2017attention,") < body.index("@article{devlin2018bert,")
    assert "brown2020language" not in body  # タグで絞り込まれている
    assert "  journal = {arXiv preprint arXiv:1706.03762}," in body
    assert "  title = {{Attention Is All You Need}}," in body
    assert "  author = {Ashish Vaswani and Noam Shazeer}," in body


def test_bibtex_escapes_and_dedupes_keys():
    class P:
        def __init__(self, arxiv_id, title):
            from datetime import date

            self.arxiv_id, self.title, self.authors, self.published = arxiv_id, title, ["A Smith"], date(2024, 1, 1)

    bib = to_bibtex([P("2401.00001", "Q&A on 100% of $k$-NN_data"), P("2401.00002", "Q&A again")])
    assert r"{{Q\&A on 100\% of $k$-NN\_data}}" in bib  # 数式の $ はそのまま
    assert "@article{smith2024qa," in bib and "@article{smith2024qaa," in bib


def test_export_bib_empty(client):
    assert client.get("/papers/export.bib").text == ""


# --- arXiv 検索 ---


def test_search_marks_registered(client, monkeypatch):
    monkeypatch.setattr(conftest, "SEARCH_RESULTS", ["1706.03762", "1810.04805"])
    p = add(client, "1706.03762")
    res = client.get("/arxiv/search?q=attention")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2 and body["start"] == 0
    assert [(i["arxiv_id"], i["paper_id"]) for i in body["items"]] == [("1706.03762", p["id"]), ("1810.04805", None)]
    assert body["items"][1]["arxiv_url"] == "https://arxiv.org/abs/1810.04805"


def test_search_errors(client):
    assert client.get("/arxiv/search?q=").status_code == 422
    assert client.get("/arxiv/search?q=x&sort=old").status_code == 422
    res = client.get("/arxiv/search?q=down")
    assert res.status_code == 502
    assert res.json()["detail"] == "arXiv に繋がらないため検索できませんでした。しばらくしてからもう一度試してください"


# --- 新着の通知 ---


def test_watch_crud(client):
    res = client.post("/watches", json={"query": "  dense   retrieval "})
    assert res.status_code == 201 and res.json()["query"] == "dense retrieval"
    assert client.post("/watches", json={"query": "dense retrieval"}).status_code == 409
    assert client.post("/watches", json={"query": ""}).status_code == 422
    assert [w["query"] for w in client.get("/watches").json()] == ["dense retrieval"]
    wid = res.json()["id"]
    assert client.delete(f"/watches/{wid}").status_code == 204
    assert client.delete(f"/watches/{wid}").status_code == 404


def test_watch_new_skips_seen_and_registered(client, monkeypatch):
    monkeypatch.setattr(conftest, "SEARCH_RESULTS", ["2005.14165", "1810.04805", "1706.03762"])
    add(client, "1706.03762")  # 登録済みは新着に出さない
    wid = client.post("/watches", json={"query": "llm"}).json()["id"]

    assert [i["arxiv_id"] for i in client.get(f"/watches/{wid}/new").json()] == ["2005.14165", "1810.04805"]

    # 知らせたものは次から出ない
    res = client.post(f"/watches/{wid}/seen", json={"arxiv_ids": ["2005.14165"]})
    assert res.status_code == 200 and res.json()["notified_at"] is not None
    assert [i["arxiv_id"] for i in client.get(f"/watches/{wid}/new").json()] == ["1810.04805"]

    # 同じ ID を何度記録しても重複しない
    client.post(f"/watches/{wid}/seen", json={"arxiv_ids": ["2005.14165", "1810.04805"]})
    assert client.get(f"/watches/{wid}/new").json() == []


def test_watch_new_404_and_arxiv_down(client):
    assert client.get("/watches/999/new").status_code == 404
    wid = client.post("/watches", json={"query": "down"}).json()["id"]
    assert client.get(f"/watches/{wid}/new").status_code == 502


# --- arXiv に 429 で断られたとき ---


def test_busy_messages(client):
    res = client.post("/papers", json={"arxiv_id": "2401.00429"})
    assert res.status_code == 503
    assert res.json()["detail"] == "arXiv が混んでいるため登録できませんでした。数分待ってから試してください"
    res = client.get("/arxiv/search?q=busy")
    assert res.status_code == 503
    assert res.json()["detail"] == "arXiv が混んでいるため検索できませんでした。数分待ってから試してください"
    res = client.post("/papers/batch", json={"items": ["1706.03762", "2401.00429"]})
    assert [i["result"] for i in res.json()] == ["busy", "busy"]

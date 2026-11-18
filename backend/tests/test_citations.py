"""引用・被引用（OpenAlex は偽物に差し替える）・読書の記録・まとめて操作・タグの管理"""

import pytest

import citations
import conftest
import scholar
from test_api import add


def work(wid, arxiv_id=None, title="T", year=2024, cited=0, refs=(), related=(), authors=("A B",)):
    """OpenAlex の応答 1 本分"""
    return {
        "id": f"https://openalex.org/{wid}",
        "doi": f"https://doi.org/10.48550/arxiv.{arxiv_id}" if arxiv_id else None,
        "title": title,
        "publication_year": year,
        "cited_by_count": cited,
        "authorships": [{"author": {"display_name": a}} for a in authors],
        "locations": [],
        "referenced_works": [f"https://openalex.org/{r}" for r in refs],
        "related_works": [f"https://openalex.org/{r}" for r in related],
    }


# 偽の OpenAlex。Attention(W1) は W2・W3 を参考文献に持ち、W4 に引用されている
WORKS = {
    "W1": work("W1", "1706.03762", "Attention Is All You Need", 2017, 150000, refs=["W2", "W3"], related=["W3"]),
    "W2": work("W2", None, "Neural <i>Machine</i> Translation", 2014, 30000),
    "W3": work("W3", "1810.04805", "BERT", 2018, 80000),
    "W4": work("W4", "2005.14165", "GPT-3", 2020, 60000, refs=["W1", "W3", "W2"]),
}
CALLS: list[str] = []


@pytest.fixture
def openalex(monkeypatch):
    CALLS.clear()

    def by_key(key):
        CALLS.append(f"work:{key}")
        for w in WORKS.values():
            if key == scholar.short_id(w["id"]) or key == scholar.arxiv_id_of(w):
                return w
        raise scholar.WorkNotFound(key)

    def by_ids(ids, fields=None):
        CALLS.append(f"ids:{','.join(ids)}")
        return {i: WORKS[i] for i in ids if i in WORKS}

    def by_arxiv(ids, fields=None):
        CALLS.append(f"arxiv:{','.join(ids)}")
        return {scholar.arxiv_id_of(w): w for w in WORKS.values() if scholar.arxiv_id_of(w) in ids}

    def citing(wid, n=30):
        CALLS.append(f"cites:{wid}")
        hits = [w for w in WORKS.values() if f"https://openalex.org/{wid}" in w["referenced_works"]]
        return len(hits), hits[:n]

    monkeypatch.setattr(scholar, "work", by_key)
    monkeypatch.setattr(scholar, "works_by_ids", by_ids)
    monkeypatch.setattr(scholar, "works_by_arxiv", by_arxiv)
    monkeypatch.setattr(scholar, "citing_works", citing)


@pytest.mark.parametrize(
    "w, expected",
    [
        ({"doi": "https://doi.org/10.48550/arxiv.1706.03762"}, "1706.03762"),
        # 学会版とまとめられた論文は DOI が学会のもの。掲載先の URL から読む
        ({"doi": "https://doi.org/10.1143/ptp.101.1155", "locations": [{"landing_page_url": "http://arxiv.org/abs/hep-th/9901001v3"}]}, "hep-th/9901001"),
        ({"doi": "https://doi.org/10.1145/x", "locations": [{"landing_page_url": "https://dl.acm.org/x"}]}, None),
    ],
)
def test_arxiv_id_of(w, expected):
    assert scholar.arxiv_id_of(w) == expected


def test_to_node_strips_tags():
    assert scholar.to_node(WORKS["W2"])["title"] == "Neural Machine Translation"


def test_map_by_arxiv_and_cache(client, openalex):
    add(client, "1810.04805")  # BERT は登録済み
    res = client.get("/citations/map?key=https://arxiv.org/abs/1706.03762v7")
    assert res.status_code == 200
    d = res.json()
    assert d["center"]["title"] == "Attention Is All You Need" and d["center"]["paper_id"] is None
    # 参考文献は被引用数の多い順。登録済みには paper_id が付く
    assert [(r["work_id"], r["paper_id"]) for r in d["references"]] == [("W3", 1), ("W2", None)]
    assert [c["work_id"] for c in d["citations"]] == ["W4"]
    assert d["references_total"] == 2 and d["citations_total"] == 1

    # 2 回目はとっておいた結果を使い、OpenAlex に問い合わせない
    CALLS.clear()
    assert client.get("/citations/map?key=1706.03762").json() == d
    assert CALLS == []


def test_map_follows_unregistered_work(client, openalex):
    # 未登録で arXiv でもない論文（W2）も、OpenAlex の ID で図が見られる
    d = client.get("/citations/map?key=W2").json()
    assert d["center"]["title"] == "Neural Machine Translation" and d["center"]["arxiv_id"] is None
    assert {c["work_id"] for c in d["citations"]} == {"W1", "W4"}


@pytest.mark.parametrize("key, status", [("hello", 400), ("9999.99999", 404), ("W9", 404)])
def test_map_errors(client, openalex, key, status):
    assert client.get(f"/citations/map?key={key}").status_code == status


def test_map_when_openalex_is_down(client, monkeypatch):
    def down(key):
        raise scholar.ScholarUnavailable(scholar.UNAVAILABLE_MESSAGE)

    monkeypatch.setattr(scholar, "work", down)
    res = client.get("/citations/map?key=1706.03762")
    assert res.status_code == 502
    assert res.json()["detail"] == "引用の情報を取得できませんでした。しばらくしてからもう一度試してください"


def test_related(client, openalex):
    add(client, "1810.04805")
    assert [(r["work_id"], r["paper_id"]) for r in client.get("/citations/related?key=1706.03762").json()] == [("W3", 1)]


def test_sync_library_and_missing(client, openalex):
    a = add(client, "1706.03762")
    b = add(client, "2005.14165")
    add(client, "hep-th/9901001")  # OpenAlex に無い
    assert client.post("/citations/sync").json() == {"synced": 2, "not_found": 1}
    # 同期したばかりなので、もう一度呼んでも問い合わせない
    CALLS.clear()
    assert client.post("/citations/sync").json() == {"synced": 0, "not_found": 0}
    assert CALLS == []

    papers = {p["arxiv_id"]: p for p in client.get("/papers").json()}
    assert papers["1706.03762"]["citation_count"] == 150000 and papers["1706.03762"]["openalex_id"] == "W1"
    assert papers["hep-th/9901001"]["citation_count"] is None

    # GPT-3 → Attention の引用だけが、登録した論文どうしの線になる
    g = client.get("/citations/library").json()
    assert g["edges"] == [{"source": b["id"], "target": a["id"]}]
    # 円の名前は登録した論文の筆頭著者と年
    assert {n["label"] for n in g["nodes"]} == {"Vaswani 2017", "Brown 2020"}
    assert g["unsynced"] == 0

    # 2 本が参考文献に挙げている未登録の W2・W3。W3（BERT）は arXiv にあるので登録できる
    m = client.get("/citations/missing").json()
    assert [(i["work_id"], i["cited_by_papers"]) for i in m] == [("W2", [a["id"], b["id"]]), ("W3", [a["id"], b["id"]])] or \
           [(i["work_id"], i["cited_by_papers"]) for i in m] == [("W3", [a["id"], b["id"]]), ("W2", [a["id"], b["id"]])]
    assert client.get("/citations/missing?min_count=3").json() == []


def test_sort_by_citations_puts_unknown_last(client, openalex):
    add(client, "1810.04805")
    add(client, "1706.03762")
    add(client, "hep-th/9901001")
    client.post("/citations/sync")
    order = [p["arxiv_id"] for p in client.get("/papers?sort=citations").json()]
    assert order == ["1706.03762", "1810.04805", "hep-th/9901001"]
    order = [p["arxiv_id"] for p in client.get("/papers?sort=citations&order=asc").json()]
    assert order == ["1810.04805", "1706.03762", "hep-th/9901001"]


def test_register_triggers_background_sync(client):
    p = add(client, "1706.03762")
    client.post("/papers/batch", json={"items": ["1810.04805", "1706.03762"]})
    assert conftest.SYNCED == [p["id"], p["id"] + 1]


# --- 読書の記録 ---


def test_read_at_is_set_and_cleared(client):
    p = add(client, "1706.03762")
    assert p["read_at"] is None
    first = client.patch(f"/papers/{p['id']}", json={"status": "read"}).json()["read_at"]
    assert first is not None
    # 「読んだ」のまま他を変えても日時は変わらない
    assert client.patch(f"/papers/{p['id']}", json={"note": "x", "status": "read"}).json()["read_at"] == first
    assert client.patch(f"/papers/{p['id']}", json={"status": "reading"}).json()["read_at"] is None


def test_stats_read(client):
    p = add(client, "1706.03762")
    client.patch(f"/papers/{p['id']}", json={"status": "read"})
    stats = client.get("/stats/read").json()
    assert len(stats["months"]) == 1 and stats["months"][0]["count"] == 1 and stats["unknown"] == 0


# --- 一覧でまとめて操作 ---


def test_bulk_tags_and_status(client):
    a = add(client, "1706.03762", tags=["nlp", "old"])
    b = add(client, "1810.04805", tags=["nlp"])
    res = client.post("/papers/bulk", json={"ids": [a["id"], b["id"]], "add_tags": ["  Survey "], "remove_tags": ["OLD"], "status": "read"})
    assert res.json() == {"updated": 2, "deleted": 0}
    papers = {p["id"]: p for p in client.get("/papers").json()}
    assert papers[a["id"]]["tags"] == ["nlp", "survey"] and papers[b["id"]]["tags"] == ["nlp", "survey"]
    assert all(p["status"] == "read" and p["read_at"] for p in papers.values())


def test_bulk_delete(client):
    a = add(client, "1706.03762")
    add(client, "1810.04805")
    assert client.post("/papers/bulk", json={"ids": [a["id"], 999], "delete": True}).json() == {"updated": 0, "deleted": 1}
    assert len(client.get("/papers").json()) == 1


def test_bulk_validation(client):
    assert client.post("/papers/bulk", json={"ids": []}).status_code == 422
    assert client.post("/papers/bulk", json={"ids": [1], "status": "done"}).status_code == 422


# --- タグの管理 ---


def test_rename_and_merge_tags(client):
    a = add(client, "1706.03762", tags=["指示追従", "意図追従"])
    b = add(client, "1810.04805", tags=["意図追従"])
    # 既にあるタグの名前にすると 1 つにまとまる（同じ論文に 2 回付かない）
    assert client.post("/tags/rename", json={"old": "意図追従", "new": "指示追従"}).json() == {"papers": 2}
    papers = {p["id"]: p["tags"] for p in client.get("/papers").json()}
    assert papers == {a["id"]: ["指示追従"], b["id"]: ["指示追従"]}
    assert client.post("/tags/rename", json={"old": "nothing", "new": "x"}).status_code == 404
    assert client.post("/tags/rename", json={"old": "指示追従", "new": "  "}).status_code == 422


def test_delete_tag(client):
    add(client, "1706.03762", tags=["nlp", "old"])
    assert client.delete("/tags/OLD").json() == {"papers": 1}
    assert client.get("/papers").json()[0]["tags"] == ["nlp"]
    assert client.delete("/tags/old").status_code == 404

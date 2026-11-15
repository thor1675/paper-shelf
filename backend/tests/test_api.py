import pytest


def add(client, arxiv_id, **fields):
    """論文を登録し、必要ならタグなどを PATCH で付けて、その論文を返す"""
    res = client.post("/papers", json={"arxiv_id": arxiv_id})
    assert res.status_code == 201, res.text
    paper = res.json()
    if fields:
        res = client.patch(f"/papers/{paper['id']}", json=fields)
        assert res.status_code == 200, res.text
        paper = res.json()
    return paper


def ids(res):
    assert res.status_code == 200, res.text
    return [p["arxiv_id"] for p in res.json()]


# --- POST /papers ---


def test_create_returns_paper_with_urls(client):
    res = client.post("/papers", json={"arxiv_id": "https://arxiv.org/abs/1706.03762v7"})
    assert res.status_code == 201
    p = res.json()
    assert p["arxiv_id"] == "1706.03762"
    assert p["title"] == "Attention Is All You Need"
    assert p["status"] == "unread" and p["tags"] == [] and p["note"] == ""
    # URL は保存せず、返すときに組み立てる
    assert p["arxiv_url"] == "https://arxiv.org/abs/1706.03762"
    assert p["pdf_url"] == "https://arxiv.org/pdf/1706.03762"


def test_create_old_style_id(client):
    assert client.post("/papers", json={"arxiv_id": "hep-th/9901001v2"}).status_code == 201


def test_create_duplicate_in_another_form_is_409(client):
    add(client, "1706.03762")
    res = client.post("/papers", json={"arxiv_id": "arXiv:1706.03762v2"})
    assert res.status_code == 409
    assert "登録済み" in res.json()["detail"]


@pytest.mark.parametrize(
    "body, status",
    [
        ({"arxiv_id": "hello"}, 400),
        ({"arxiv_id": "9999.99999"}, 404),
        ({"arxiv_id": "2401.00502"}, 502),
        ({}, 422),
        ({"arxiv_id": "1706.03762", "tags": ["x"]}, 422),
    ],
)
def test_create_errors(client, body, status):
    res = client.post("/papers", json=body)
    assert res.status_code == status
    assert isinstance(res.json()["detail"], str)


@pytest.mark.parametrize(
    "arxiv_id, detail",
    [
        ("hello", "arXiv ID の形式ではありません: hello"),
        ("9999.99999", "arXiv ID: 9999.99999はarXivにありませんでした"),
        ("2401.00502", "arXiv に繋がらないため登録できませんでした。しばらくしてからもう一度試してください"),
    ],
)
def test_create_error_messages(client, arxiv_id, detail):
    assert client.post("/papers", json={"arxiv_id": arxiv_id}).json()["detail"] == detail


def test_messages_have_no_trailing_period(client):
    # 表記の方針：文末に「。」を付けない
    add(client, "1706.03762")
    for res in [
        client.post("/papers", json={"arxiv_id": "1706.03762"}),
        client.post("/papers", json={"arxiv_id": "9999.99999"}),
        client.post("/papers", json={"arxiv_id": "2401.00502"}),
        client.get("/papers/999"),
        client.patch("/papers/1", json={"title": "x"}),
    ]:
        assert not res.json()["detail"].endswith("。"), res.json()["detail"]


# --- GET /papers ---


@pytest.fixture
def three(client):
    add(client, "1706.03762", tags=["NLP", "transformer"], status="read")
    add(client, "1810.04805", tags=["nlp", "pretraining"], status="reading")
    add(client, "2005.14165", tags=["nlp", "llm"])
    return client


def test_list_default_order_is_newest_added_first(three):
    assert ids(three.get("/papers")) == ["2005.14165", "1810.04805", "1706.03762"]


def test_list_sort_by_published(three):
    assert ids(three.get("/papers?sort=published&order=asc")) == ["1706.03762", "1810.04805", "2005.14165"]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("tag=nlp", {"1706.03762", "1810.04805", "2005.14165"}),
        ("tag=NLP", {"1706.03762", "1810.04805", "2005.14165"}),  # 大文字でも一致
        ("tag=nlp&tag=llm", {"2005.14165"}),  # 複数は AND
        ("tag=nothing", set()),
        ("status=read", {"1706.03762"}),
        ("author=devlin", {"1810.04805"}),  # 部分一致・大文字小文字を区別しない
        ("author=Vaswani%20Noam", set()),  # 2 人の名前にまたがって一致しない
        ("q=bert", {"1810.04805"}),
        ("q=%25", {"1810.04805"}),  # % は文字として検索（abstract に 80.5% がある）
        ("q=_", set()),  # _ も文字として検索
        ("tag=nlp&status=reading", {"1810.04805"}),
    ],
)
def test_list_filters(three, query, expected):
    assert set(ids(three.get(f"/papers?{query}"))) == expected


def test_list_invalid_status_is_japanese_422(client):
    res = client.get("/papers?status=done")
    assert res.status_code == 422
    assert res.json()["detail"] == "「status」は unread / reading / read のどれかにしてください"


# --- GET / PATCH / DELETE /papers/{id} ---


def test_get_one_and_404(client):
    p = add(client, "1706.03762")
    assert client.get(f"/papers/{p['id']}").json()["title"] == "Attention Is All You Need"
    assert client.get("/papers/999").status_code == 404
    assert client.get("/papers/abc").json()["detail"] == "「paper_id」は整数にしてください"


def test_patch_normalizes_tags(client):
    p = add(client, "1706.03762")
    res = client.patch(f"/papers/{p['id']}", json={"tags": ["  NLP ", "Transformer", "nlp", ""]})
    assert res.json()["tags"] == ["nlp", "transformer"]


def test_patch_only_changes_sent_fields(client):
    p = add(client, "1706.03762", tags=["nlp"], note="memo")
    res = client.patch(f"/papers/{p['id']}", json={"status": "read"})
    assert res.json()["tags"] == ["nlp"] and res.json()["note"] == "memo"
    # タグを全部消すときは空のリスト
    assert client.patch(f"/papers/{p['id']}", json={"tags": []}).json()["tags"] == []


@pytest.mark.parametrize(
    "body, detail",
    [
        ({"title": "x"}, "受け付けていない項目です: title"),
        ({"title": "x", "authors": []}, "受け付けていない項目です: title, authors"),
        ({"note": None}, "null は使えません: note"),
        ({"status": "done"}, "「status」は unread / reading / read のどれかにしてください"),
        ({"tags": "nlp"}, "「tags」は配列にしてください"),
        ({"tags": [1]}, "「tags」は文字列にしてください"),
    ],
)
def test_patch_rejects_bad_input(client, body, detail):
    p = add(client, "1706.03762")
    res = client.patch(f"/papers/{p['id']}", json=body)
    assert res.status_code == 422
    assert res.json()["detail"] == detail
    # 駄目な項目が混ざっていたら何も変わらない
    assert client.get(f"/papers/{p['id']}").json()["note"] == ""


def test_patch_404(client):
    assert client.patch("/papers/999", json={"note": "x"}).status_code == 404


def test_delete(client):
    p = add(client, "1706.03762")
    assert client.delete(f"/papers/{p['id']}").status_code == 204
    assert client.delete(f"/papers/{p['id']}").status_code == 404
    assert client.get("/papers").json() == []


# --- 集計 ---


def test_tags_counts(three):
    assert three.get("/tags").json()[:2] == [
        {"name": "nlp", "count": 3},
        {"name": "llm", "count": 1},
    ]


def test_stats_years(three):
    assert three.get("/stats/years").json() == [
        {"year": 2017, "count": 1},
        {"year": 2018, "count": 1},
        {"year": 2020, "count": 1},
    ]


def test_graph_tags(three):
    g = three.get("/graph/tags").json()
    assert g["nodes"][0] == {"id": "nlp", "count": 3}
    edges = {(e["source"], e["target"]): e["weight"] for e in g["edges"]}
    assert edges == {("nlp", "transformer"): 1, ("nlp", "pretraining"): 1, ("llm", "nlp"): 1}


def test_graph_authors_filters(client, monkeypatch):
    import conftest

    # 同じ 2 人が 2 本で共著、そのうち 1 本は著者が多い
    monkeypatch.setitem(conftest.FAKE_PAPERS, "2401.00001", {
        "title": "A", "authors": ["Alice", "Bob"], "abstract": "-", "published": "2024-01-01"})
    monkeypatch.setitem(conftest.FAKE_PAPERS, "2401.00002", {
        "title": "B", "authors": ["Alice", "Bob", "Carol", "Dave"], "abstract": "-", "published": "2024-01-02"})
    add(client, "2401.00001")
    add(client, "2401.00002")

    g = client.get("/graph/authors").json()  # 既定: 2 本以上・20 人以下
    assert g["nodes"] == [{"id": "Alice", "count": 2}, {"id": "Bob", "count": 2}]
    assert g["edges"] == [{"source": "Alice", "target": "Bob", "weight": 2}]

    # 著者が 3 人を超える論文を除くと、2 本以上の著者はいなくなる
    assert client.get("/graph/authors?max_authors=3").json()["nodes"] == []
    assert client.get("/graph/authors?min_papers=0").status_code == 422

"""
テストは本番とは別の DB（papershelf_test）で動かす。
DATABASE_URL を差し替えてから db.py / main.py を import するので、このファイルが最初に読まれる必要がある
"""

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

TEST_DB = "papershelf_test"
BASE_URL = os.environ["DATABASE_URL"]
TEST_URL = BASE_URL.rsplit("/", 1)[0] + "/" + TEST_DB
# 本番の DB に向いたままテストが走ると論文が消えるので、必ず止める
assert TEST_URL.endswith("/" + TEST_DB) and TEST_URL != BASE_URL
os.environ["DATABASE_URL"] = TEST_URL

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def test_database():
    # テスト用 DB が無ければ作り、マイグレーションを最新まで当てる（マイグレーション自体のテストも兼ねる）
    with psycopg.connect(BASE_URL, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def client(monkeypatch):
    """毎回空の papers テーブルから始める TestClient。arXiv への問い合わせは偽物に差し替える"""
    from fastapi.testclient import TestClient

    import main

    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE papers, shelf, watches, scholar_cache, translations, users, user_sessions, invites, "
            "slack_link_codes RESTART IDENTITY CASCADE"
        )

    monkeypatch.setattr(main, "fetch_paper", fake_fetch_paper)
    monkeypatch.setattr(main, "fetch_papers", fake_fetch_papers)
    monkeypatch.setattr(main, "search_arxiv", fake_search_arxiv)
    # 登録直後の OpenAlex との同期は、テストでは呼ばれたことだけ記録する
    SYNCED.clear()
    monkeypatch.setattr(main, "sync_new_papers", SYNCED.extend)
    # 翻訳は裏の処理をテストの DB で動かす（本番の DB に繋がないように）
    import db as db_module
    from sqlmodel import Session as _Session

    def run_translation(arxiv_id):
        with _Session(db_module.engine) as s:
            main.translation.run(s, arxiv_id)

    monkeypatch.setattr(main, "run_translation", run_translation)
    # 最初の 1 人（alice）として登録し、ログインした状態で返す（Cookie は TestClient が持つ）
    c = TestClient(main.app)
    assert c.post("/auth/register", json={"username": "alice", "password": "password-a"}).status_code == 201
    return c


@pytest.fixture
def other_client(client):
    """2 人目（bob）。alice の招待コードで登録し、ログインした状態で返す"""
    from fastapi.testclient import TestClient

    import main

    code = client.post("/auth/invites").json()["code"]
    c = TestClient(main.app)
    res = c.post("/auth/register", json={"username": "bob", "password": "password-b", "invite_code": code})
    assert res.status_code == 201, res.text
    return c


SYNCED: list[int] = []


# 偽の arXiv。ID ごとに返すメタデータを決めておく
FAKE_PAPERS = {
    "1706.03762": {
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer"],
        "abstract": "The dominant sequence transduction models ...",
        "published": "2017-06-12",
    },
    "1810.04805": {
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "authors": ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee"],
        "abstract": "We introduce a new language representation model called BERT, 80.5% on GLUE.",
        "published": "2018-10-11",
    },
    "2005.14165": {
        "title": "Language Models are Few-Shot Learners",
        "authors": ["Tom B. Brown", "Benjamin Mann"],
        "abstract": "Recent work has demonstrated substantial gains ...",
        "published": "2020-05-28",
    },
    "hep-th/9901001": {
        "title": "An old-style paper",
        "authors": ["Someone"],
        "abstract": "Old identifiers still work.",
        "published": "1999-01-04",
    },
}


def fake_fetch_paper(arxiv_id: str) -> dict:
    from datetime import date

    from arxiv import UNAVAILABLE_MESSAGE, ArxivUnavailable, PaperNotFound

    if arxiv_id == "2401.00502":  # arXiv が落ちている場合の代わり
        raise ArxivUnavailable(UNAVAILABLE_MESSAGE)
    if arxiv_id == "2401.00429":  # arXiv に 429 で断られた場合の代わり
        from arxiv import BUSY_MESSAGE, ArxivBusy

        raise ArxivBusy(BUSY_MESSAGE)
    if arxiv_id not in FAKE_PAPERS:
        raise PaperNotFound(f"arXiv ID: {arxiv_id}はarXivにありませんでした")
    p = FAKE_PAPERS[arxiv_id]
    return {**p, "arxiv_id": arxiv_id, "published": date.fromisoformat(p["published"])}


def fake_fetch_papers(arxiv_ids: list[str]) -> dict[str, dict]:
    from arxiv import ArxivUnavailable, PaperNotFound

    if "2401.00502" in arxiv_ids:
        from arxiv import UNAVAILABLE_MESSAGE

        raise ArxivUnavailable(UNAVAILABLE_MESSAGE)
    if "2401.00429" in arxiv_ids:
        from arxiv import BUSY_MESSAGE, ArxivBusy

        raise ArxivBusy(BUSY_MESSAGE)
    result = {}
    for i in arxiv_ids:
        try:
            result[i] = fake_fetch_paper(i)
        except PaperNotFound:
            pass  # 本物の arXiv と同じく、無い ID は黙って外す
    return result


# 偽の arXiv 検索。テストごとに SEARCH_RESULTS を書き換えて使う
SEARCH_RESULTS: list[str] = []


def fake_search_arxiv(q, start=0, max_results=20, newest=False):
    from arxiv import ArxivUnavailable, UNAVAILABLE_MESSAGE

    if q == "down":
        raise ArxivUnavailable(UNAVAILABLE_MESSAGE)
    if q == "busy":
        from arxiv import SEARCH_BUSY_MESSAGE, ArxivBusy

        raise ArxivBusy(SEARCH_BUSY_MESSAGE)
    papers = [fake_fetch_paper(i) for i in SEARCH_RESULTS]
    return len(papers), papers[start : start + max_results]

"""ログイン・招待コード・人ごとの本棚・Slack との紐づけ"""

import psycopg
import pytest
from fastapi.testclient import TestClient

import auth
import main
from conftest import TEST_URL


def add(c, arxiv_id):
    res = c.post("/papers", json={"arxiv_id": arxiv_id})
    assert res.status_code == 201, res.text
    return res.json()


# --- 登録・ログイン ---


def test_requires_login(client):
    anon = TestClient(main.app)
    for method, url in [("get", "/papers"), ("post", "/papers"), ("get", "/tags"), ("get", "/watches"), ("get", "/citations/library")]:
        res = getattr(anon, method)(url)
        assert res.status_code == 401 and res.json()["detail"] == "ログインしてください"


def test_setup_and_invite_required(client):
    anon = TestClient(main.app)
    assert anon.get("/auth/setup").json()["needs_setup"] is False
    res = anon.post("/auth/register", json={"username": "bob", "password": "password-b"})
    assert res.status_code == 403 and "招待コード" in res.json()["detail"]
    res = anon.post("/auth/register", json={"username": "bob", "password": "password-b", "invite_code": "NOPE"})
    assert res.status_code == 403


def test_invite_is_single_use(client):
    code = client.post("/auth/invites").json()["code"]
    assert [i["code"] for i in client.get("/auth/invites").json()] == [code]
    ok = TestClient(main.app).post("/auth/register", json={"username": "bob", "password": "password-b", "invite_code": code.lower()})
    assert ok.status_code == 201
    again = TestClient(main.app).post("/auth/register", json={"username": "carol", "password": "password-c", "invite_code": code})
    assert again.status_code == 403
    assert client.get("/auth/invites").json() == []


def test_register_validation(client):
    code = client.post("/auth/invites").json()["code"]
    anon = TestClient(main.app)
    res = anon.post("/auth/register", json={"username": "ab", "password": "password-x", "invite_code": code})
    assert res.status_code == 422 and res.json()["detail"] == "ユーザー名は半角英数字と _ - で 3〜32 文字にしてください"
    res = anon.post("/auth/register", json={"username": "bob", "password": "short", "invite_code": code})
    assert res.json()["detail"] == "パスワードは 8 文字以上にしてください"
    res = anon.post("/auth/register", json={"username": "alice", "password": "password-x", "invite_code": code})
    assert res.status_code == 409


def test_login_logout(client):
    anon = TestClient(main.app)
    assert anon.post("/auth/login", json={"username": "alice", "password": "wrong-pass"}).status_code == 401
    assert anon.post("/auth/login", json={"username": "nobody", "password": "wrong-pass"}).json()["detail"] == "ユーザー名かパスワードが違います"
    res = anon.post("/auth/login", json={"username": "alice", "password": "password-a"})
    assert res.status_code == 200 and res.json() == {"id": 1, "username": "alice", "slack_linked": False, "github_login": None}
    # Cookie は HttpOnly
    assert "httponly" in res.headers["set-cookie"].lower()
    assert anon.get("/auth/me").json()["username"] == "alice"
    assert anon.post("/auth/logout").status_code == 204
    assert anon.get("/auth/me").status_code == 401


def test_password_is_hashed(client):
    with psycopg.connect(TEST_URL) as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE username = 'alice'").fetchone()[0]
    assert "password-a" not in stored and stored.startswith("scrypt$")
    assert auth.verify_password("password-a", stored) and not auth.verify_password("password-b", stored)


def test_first_user_takes_over_existing_data(client):
    # ログインを付ける前の論文（持ち主が NULL）は、最初に登録した人のものになる
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE users RESTART IDENTITY CASCADE")
        pid = conn.execute(
            "INSERT INTO papers (arxiv_id, title, authors, abstract, published) "
            "VALUES ('1706.03762', 'Attention', '{A}', 'x', '2017-06-12') RETURNING id"
        ).fetchone()[0]
        conn.execute("INSERT INTO shelf (user_id, paper_id, tags, created_at) VALUES (NULL, %s, '{nlp}', now())", (pid,))
        conn.execute("INSERT INTO watches (user_id, query, created_at) VALUES (NULL, 'rag', now())")
    first = TestClient(main.app)
    assert first.get("/auth/setup").json()["needs_setup"] is True
    assert first.post("/auth/register", json={"username": "carol", "password": "password-c"}).status_code == 201
    assert [(p["arxiv_id"], p["tags"]) for p in first.get("/papers").json()] == [("1706.03762", ["nlp"])]
    assert [w["query"] for w in first.get("/watches").json()] == ["rag"]


# --- ユーザー名・パスワードの変更 ---


def test_change_username(client, other_client):
    res = client.patch("/auth/username", json={"username": "alice2", "current_password": "wrong-pass"})
    assert res.status_code == 403 and res.json()["detail"] == auth.WRONG_PASSWORD
    res = client.patch("/auth/username", json={"username": "bob", "current_password": "password-a"})
    assert res.status_code == 409
    res = client.patch("/auth/username", json={"username": "a", "current_password": "password-a"})
    assert res.status_code == 422
    res = client.patch("/auth/username", json={"username": "alice2", "current_password": "password-a"})
    assert res.status_code == 200 and res.json()["username"] == "alice2"
    assert client.get("/auth/me").json()["username"] == "alice2"
    anon = TestClient(main.app)
    assert anon.post("/auth/login", json={"username": "alice", "password": "password-a"}).status_code == 401
    assert anon.post("/auth/login", json={"username": "alice2", "password": "password-a"}).status_code == 200


def test_change_password_logs_out_other_devices(client):
    other_device = TestClient(main.app)
    assert other_device.post("/auth/login", json={"username": "alice", "password": "password-a"}).status_code == 200
    res = client.post("/auth/password", json={"current_password": "wrong-pass", "new_password": "password-new"})
    assert res.status_code == 403
    res = client.post("/auth/password", json={"current_password": "password-a", "new_password": "short"})
    assert res.json()["detail"] == "パスワードは 8 文字以上にしてください"
    assert client.post("/auth/password", json={"current_password": "password-a", "new_password": "password-new"}).status_code == 204
    # 今の端末はログインしたまま、ほかの端末はログアウト
    assert client.get("/auth/me").status_code == 200
    assert other_device.get("/auth/me").status_code == 401
    anon = TestClient(main.app)
    assert anon.post("/auth/login", json={"username": "alice", "password": "password-a"}).status_code == 401
    assert anon.post("/auth/login", json={"username": "alice", "password": "password-new"}).status_code == 200


# --- 人ごとの本棚 ---


def test_shelves_are_separate(client, other_client, monkeypatch):
    a = add(client, "1706.03762")
    client.patch(f"/papers/{a['id']}", json={"tags": ["nlp"], "note": "alice のメモ", "status": "read"})

    # bob からは alice の論文は見えない
    assert other_client.get("/papers").json() == []
    assert other_client.get(f"/papers/{a['id']}").status_code == 404
    assert other_client.patch(f"/papers/{a['id']}", json={"note": "x"}).status_code == 404
    assert other_client.delete(f"/papers/{a['id']}").status_code == 404
    assert other_client.get("/tags").json() == []

    # bob が同じ論文を登録すると、arXiv に問い合わせずに bob の本棚に入る（ステータスなどは別）
    monkeypatch.setattr(main, "fetch_paper", lambda _: pytest.fail("arXiv に問い合わせてはいけない"))
    b = add(other_client, "1706.03762")
    assert b["id"] == a["id"] and b["tags"] == [] and b["note"] == "" and b["status"] == "unread"
    assert other_client.post("/papers", json={"arxiv_id": "1706.03762"}).status_code == 409

    # bob が本棚から外しても、alice の本棚には残る
    assert other_client.delete(f"/papers/{b['id']}").status_code == 204
    mine = client.get(f"/papers/{a['id']}").json()
    assert mine["note"] == "alice のメモ" and mine["status"] == "read"


def test_batch_uses_known_papers(client, other_client, monkeypatch):
    add(client, "1706.03762")
    monkeypatch.setattr(main, "fetch_papers", lambda ids: pytest.fail("arXiv に問い合わせてはいけない") if ids else {})
    res = other_client.post("/papers/batch", json={"items": ["1706.03762"]}).json()
    assert [i["result"] for i in res] == ["created"]
    res = other_client.post("/papers/batch", json={"items": ["1706.03762"]}).json()
    assert [i["result"] for i in res] == ["exists"]


def test_search_marks_only_own_papers(client, other_client):
    import conftest

    add(client, "1706.03762")
    conftest.SEARCH_RESULTS[:] = ["1706.03762"]
    assert client.get("/arxiv/search?q=x").json()["items"][0]["paper_id"] is not None
    assert other_client.get("/arxiv/search?q=x").json()["items"][0]["paper_id"] is None


def test_watches_are_separate(client, other_client):
    w = client.post("/watches", json={"query": "rag"}).json()
    # 同じ語を別の人が登録できる
    assert other_client.post("/watches", json={"query": "rag"}).status_code == 201
    assert len(other_client.get("/watches").json()) == 1
    assert other_client.delete(f"/watches/{w['id']}").status_code == 404
    assert other_client.get(f"/watches/{w['id']}/new").status_code == 404


def test_translation_needs_paper_on_shelf(client, other_client):
    a = add(client, "1706.03762")
    assert other_client.get(f"/papers/{a['id']}/translation").status_code == 404
    assert other_client.get(f"/papers/{a['id']}/translation.html").status_code == 404


# --- slackbot と Slack の紐づけ ---


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setattr(auth, "BOT_TOKEN", "secret-bot-token")
    return TestClient(main.app, headers={"X-Bot-Token": "secret-bot-token"})


def test_bot_needs_linked_slack_user(client, bot):
    res = bot.post("/papers", json={"arxiv_id": "1706.03762"}, headers={"X-Slack-User": "U123"})
    assert res.status_code == 403 and res.json()["detail"] == auth.NOT_LINKED
    wrong = TestClient(main.app, headers={"X-Bot-Token": "wrong", "X-Slack-User": "U123"})
    assert wrong.get("/papers").status_code == 401


def test_bot_token_disabled_when_unset(client, monkeypatch):
    monkeypatch.setattr(auth, "BOT_TOKEN", "")
    res = TestClient(main.app, headers={"X-Bot-Token": ""}).post("/bot/slack-link", json={"code": "x", "slack_user_id": "U1"})
    assert res.status_code == 401


def test_slack_link_flow(client, other_client, bot):
    code = client.post("/auth/slack-link-code").json()["code"]
    assert code.startswith("ps-link-")
    assert bot.post("/bot/slack-link", json={"code": "ps-link-WRONG", "slack_user_id": "U123"}).status_code == 404
    res = bot.post("/bot/slack-link", json={"code": code, "slack_user_id": "U123"})
    assert res.status_code == 200 and res.json()["username"] == "alice"
    assert client.get("/auth/me").json()["slack_linked"] is True
    # コードは 1 回だけ
    assert bot.post("/bot/slack-link", json={"code": code, "slack_user_id": "U123"}).status_code == 404

    # 紐づけた人として登録でき、alice の本棚に入る
    res = bot.post("/papers", json={"arxiv_id": "1706.03762"}, headers={"X-Slack-User": "U123"})
    assert res.status_code == 201
    assert [p["arxiv_id"] for p in client.get("/papers").json()] == ["1706.03762"]
    assert other_client.get("/papers").json() == []

    # 同じ Slack アカウントは別の人には紐づけられない
    bob_code = other_client.post("/auth/slack-link-code").json()["code"]
    res = bot.post("/bot/slack-link", json={"code": bob_code, "slack_user_id": "U123"})
    assert res.status_code == 409 and "alice" in res.json()["detail"]

    # 紐づけを外すと Slack からは保存できない
    assert client.delete("/auth/slack-link").status_code == 204
    assert bot.post("/papers", json={"arxiv_id": "1810.04805"}, headers={"X-Slack-User": "U123"}).status_code == 403


def test_bot_cannot_change_account(client, bot):
    code = client.post("/auth/slack-link-code").json()["code"]
    bot.post("/bot/slack-link", json={"code": code, "slack_user_id": "U123"})
    h = {"X-Slack-User": "U123"}
    assert bot.patch("/auth/username", json={"username": "evil", "current_password": "password-a"}, headers=h).status_code == 403
    assert bot.post("/auth/password", json={"current_password": "password-a", "new_password": "password-new"}, headers=h).status_code == 403


def test_bot_watches_lists_linked_users_only(client, other_client, bot):
    client.post("/watches", json={"query": "rag"})
    other_client.post("/watches", json={"query": "colbert"})
    code = client.post("/auth/slack-link-code").json()["code"]
    bot.post("/bot/slack-link", json={"code": code, "slack_user_id": "U123"})
    rows = bot.get("/bot/watches").json()
    assert [(w["query"], w["slack_user_id"]) for w in rows] == [("rag", "U123")]
    assert TestClient(main.app).get("/bot/watches").status_code == 401

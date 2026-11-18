import httpx
import pytest

import bot


@pytest.mark.parametrize(
    "text, expected",
    [
        ("見て <https://arxiv.org/abs/1810.04805v2|BERT> と <https://arxiv.org/pdf/1706.03762v7.pdf>",
         ["1810.04805", "1706.03762"]),
        ("https://arxiv.org/html/2401.12345v1", ["2401.12345"]),
        ("https://www.arxiv.org/abs/2401.12345", ["2401.12345"]),
        ("arXiv:2005.14165 と ARXIV: hep-th/9901001v2", ["2005.14165", "hep-th/9901001"]),
        ("重複 arXiv:2005.14165 https://arxiv.org/abs/2005.14165", ["2005.14165"]),
        ("2024.12345 は日付っぽいので拾わない", []),
        ("arxiv.org/abs/2401.123456", []),  # ID の一部だけを拾わない
        ("https://fooarxiv.org/abs/2401.12345", []),
        ("xarXiv:2401.12345", []),
        ("https://example.com/abs/1234.56789", []),
    ],
)
def test_extract_arxiv_ids(text, expected):
    assert bot.extract_arxiv_ids(text) == expected


def test_slack_to_markdown():
    text = "<@U1> これ &amp; <https://x.org|a [b]> <#C1|papers> <!here> <!subteam^S1|@team>"
    assert bot.slack_to_markdown(text, lambda uid: "taro") == (
        "@taro これ & [a \\[b\\]](https://x.org) #papers @here @team"
    )


def test_build_note():
    note = bot.build_note("これ良さそう\n\n実験が面白い", "ryousei", "papers", "https://slack/p1")
    assert note == "> これ良さそう\n>\n> 実験が面白い\n\n— #papers で @ryousei が投稿（[Slack で開く](https://slack/p1)）"


# --- メッセージを受け取ったときの処理（Slack と backend は偽物） ---


class FakeClient:
    def __init__(self):
        self.reactions: list[str] = []
        self.ephemeral: list[dict] = []

    def chat_postEphemeral(self, **kw):
        self.ephemeral.append(kw)

    def users_info(self, user):
        return {"user": {"profile": {"display_name": "ryousei"}}}

    def conversations_info(self, channel):
        return {"channel": {"name": "papers"}}

    def chat_getPermalink(self, channel, message_ts):
        return {"permalink": "https://slack/p1"}

    def reactions_add(self, channel, timestamp, name):
        self.reactions.append(name)


class FakeBackend:
    """POST /papers の結果を ID ごとに決めておき、PATCH で書かれたメモを記録する"""

    def __init__(self, results: dict[str, int], patch_fails: bool = False):
        self.results, self.patch_fails = results, patch_fails
        self.notes: dict[int, str] = {}
        self.headers: list[dict] = []
        self.links: list[dict] = []

    def post(self, url, json, timeout, headers=None):
        self.headers.append(headers)
        if url.endswith("/bot/slack-link"):
            self.links.append(json)
            ok = json["code"] == "ps-link-ABCD2345"
            return httpx.Response(200 if ok else 404, json={"username": "alice"} if ok else {"detail": "期限切れ"},
                                  request=httpx.Request("POST", url))
        code = self.results[json["arxiv_id"]]
        if code == 403:
            return httpx.Response(403, json={"detail": "紐づいていません"}, request=httpx.Request("POST", url))
        if code == -1:
            raise httpx.ConnectError("down")
        return httpx.Response(code, json={"id": 1} if code == 201 else {"detail": "x"},
                              request=httpx.Request("POST", url))

    def patch(self, url, json, timeout, headers=None):
        status = 500 if self.patch_fails else 200
        if not self.patch_fails:
            self.notes[int(url.rsplit("/", 1)[1])] = json["note"]
        return httpx.Response(status, json={}, request=httpx.Request("PATCH", url))


@pytest.fixture
def run(monkeypatch):
    class Logger:
        def warning(self, *a): pass
        def info(self, *a): pass

    class App:
        def event(self, name):
            def deco(f):
                self.handler = f
                return f
            return deco

        def action(self, action_id):
            return lambda f: f

    def _run(text, backend, **event):
        monkeypatch.setattr(bot.httpx, "post", backend.post)
        monkeypatch.setattr(bot.httpx, "patch", backend.patch)
        app, client = App(), FakeClient()
        bot.register(app)
        app.handler({"channel": "C1", "ts": "1.0", "user": "U1", "text": text, **event}, client, Logger())
        backend.client = client
        return client.reactions

    return _run


def test_new_paper_gets_check_and_note(run):
    backend = FakeBackend({"1810.04805": 201})
    assert run("これ良さそう <https://arxiv.org/abs/1810.04805>", backend) == ["white_check_mark"]
    assert backend.notes[1].startswith("> これ良さそう https://arxiv.org/abs/1810.04805")
    assert "— #papers で @ryousei が投稿" in backend.notes[1]


@pytest.mark.parametrize(
    "results, reactions",
    [
        ({"1810.04805": 409}, ["eyes"]),
        ({"1810.04805": 404}, ["warning"]),
        ({"1810.04805": -1}, ["warning"]),  # backend に繋がらない
    ],
)
def test_reactions(run, results, reactions):
    assert run("arXiv:1810.04805", FakeBackend(results)) == reactions


def test_mixed_results_get_each_reaction_once(run):
    backend = FakeBackend({"9999.99999": 404, "1810.04805": 409, "1706.03762": 409})
    assert run("arXiv:9999.99999 arXiv:1810.04805 arXiv:1706.03762", backend) == ["warning", "eyes"]


def test_note_failure_keeps_check(run):
    # 論文は保存できたので、メモの書き込みに失敗しても ✅
    assert run("arXiv:1810.04805", FakeBackend({"1810.04805": 201}, patch_fails=True)) == ["white_check_mark"]


@pytest.mark.parametrize("event", [{"bot_id": "B1"}, {"subtype": "message_changed"}, {"subtype": "message_deleted"}])
def test_ignored_messages(run, event):
    assert run("arXiv:1810.04805", FakeBackend({}), **event) == []


def test_message_without_link(run):
    assert run("こんにちは", FakeBackend({})) == []


def test_sends_bot_token_and_slack_user(run, monkeypatch):
    # backend には合言葉と、投稿した人の Slack ID を送る（その人の本棚に入る）
    monkeypatch.setattr(bot, "BOT_TOKEN", "secret")
    backend = FakeBackend({"1810.04805": 201})
    run("arXiv:1810.04805", backend)
    assert backend.headers[0] == {"X-Bot-Token": "secret", "X-Slack-User": "U1"}


def test_unlinked_user_gets_ephemeral_and_no_reaction(run):
    backend = FakeBackend({"1810.04805": 403, "1706.03762": 201})
    assert run("arXiv:1810.04805 arXiv:1706.03762", backend) == []
    assert backend.client.ephemeral == [{"channel": "C1", "user": "U1", "text": "紐づいていません"}]
    # 1 本目で分かったので、2 本目は送らない
    assert len(backend.headers) == 1


@pytest.mark.parametrize(
    "code, text",
    [
        ("ps-link-ABCD2345", "PAPER - Shelf の「alice」と紐づけました。リンクを貼ると、あなたの本棚に保存されます"),
        ("ps-link-ZZZZ2345", "期限切れ"),
    ],
)
def test_link_code(run, code, text):
    backend = FakeBackend({})
    assert run(f"{code}", backend) == []
    assert backend.links == [{"code": code, "slack_user_id": "U1"}]
    assert backend.client.ephemeral[0]["text"] == text

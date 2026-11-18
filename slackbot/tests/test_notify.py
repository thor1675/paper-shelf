from datetime import datetime

import httpx
import pytest

import bot
import notify


def paper(i: int, authors=("A", "B")) -> dict:
    return {
        "arxiv_id": f"2611.0000{i}",
        "title": f"Paper <{i}> & more",
        "authors": list(authors),
        "published": "2026-11-16",
        "arxiv_url": f"https://arxiv.org/abs/2611.0000{i}",
    }


def test_build_blocks():
    blocks = notify.build_blocks("dense retrieval", [paper(1, ["A", "B", "C", "D", "E"])])
    assert blocks[0]["text"]["text"] == "*「dense retrieval」の新着 1 本*"
    item = blocks[1]
    # Slack の特別な文字はエスケープする
    assert item["text"]["text"] == "<https://arxiv.org/abs/2611.00001|Paper &lt;1&gt; &amp; more>\nA, B, C 他2人 · 2026-11-16"
    assert item["accessory"]["action_id"] == "save_paper" and item["accessory"]["value"] == "2611.00001"


def test_build_blocks_caps_items():
    blocks = notify.build_blocks("q", [paper(i % 10) for i in range(25)])
    assert len(blocks) == 1 + notify.MAX_ITEMS + 1
    assert "ほか 5 本" in blocks[-1]["elements"][0]["text"]


@pytest.mark.parametrize(
    "now, hours",
    [
        ("2026-11-17T08:00:00+09:00", 1),
        ("2026-11-17T09:00:00+09:00", 24),  # ちょうど 9 時なら次の日
        ("2026-11-17T23:30:00+09:00", 9.5),
        ("2026-11-17T00:00:00+00:00", 24),  # UTC 0 時 = 日本時間 9 時
    ],
)
def test_seconds_until(now, hours):
    assert notify.seconds_until(9, datetime.fromisoformat(now)) == hours * 3600


class FakeSlack:
    def __init__(self, fail=False):
        self.posts, self.fail = [], fail

    def chat_postMessage(self, **kw):
        if self.fail:
            raise RuntimeError("channel_not_found")
        self.posts.append(kw)


@pytest.fixture
def backend(monkeypatch):
    """GET /watches と /watches/{id}/new を返し、POST /watches/{id}/seen を記録する偽の backend"""
    state = {
        "watches": [{"id": 1, "query": "a", "slack_user_id": "U1"}, {"id": 2, "query": "b", "slack_user_id": "U2"}],
        "new": {1: [paper(1), paper(2)], 2: []},
        "seen": {},
        "down": set(),
        "headers": [],
    }

    def get(url, timeout, headers=None):
        state["headers"].append((url, headers))
        req = httpx.Request("GET", url)
        if url.endswith("/bot/watches"):
            return httpx.Response(200, json=state["watches"], request=req)
        wid = int(url.split("/")[-2])
        if wid in state["down"]:
            return httpx.Response(502, json={"detail": "x"}, request=req)
        return httpx.Response(200, json=state["new"][wid], request=req)

    def post(url, json, timeout, headers=None):
        state["seen"][int(url.split("/")[-2])] = json["arxiv_ids"]
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(notify.httpx, "get", get)
    monkeypatch.setattr(notify.httpx, "post", post)
    return state


def test_notify_posts_and_records_seen(backend):
    slack = FakeSlack()
    assert notify.notify_all(slack, "C1") == 2
    # 新着の無いキーワードは投稿しない
    assert len(slack.posts) == 1 and slack.posts[0]["channel"] == "C1"
    assert backend["seen"] == {1: ["2611.00001", "2611.00002"]}
    # キーワードを登録した人をメンションし、その人として新着を調べる
    assert slack.posts[0]["blocks"][0]["text"]["text"].startswith("<@U1> ")
    assert [h["X-Slack-User"] for u, h in backend["headers"] if "/new" in u] == ["U1", "U2"]


def test_notify_does_not_record_when_post_fails(backend):
    # 投稿に失敗したら「知らせた」と記録しない（次の日にまた出す）
    assert notify.notify_all(FakeSlack(fail=True), "C1") == 0
    assert backend["seen"] == {}


def test_notify_continues_after_one_keyword_fails(backend):
    backend["watches"].append({"id": 3, "query": "c", "slack_user_id": "U3"})
    backend["new"][3] = [paper(3)]
    backend["down"].add(1)
    slack = FakeSlack()
    assert notify.notify_all(slack, "C1") == 1
    assert backend["seen"] == {3: ["2611.00003"]}


# --- 「保存」ボタン ---


class Logger:
    def warning(self, *a): pass
    def info(self, *a): pass


@pytest.mark.parametrize(
    "status, body, text",
    [
        (201, {"title": "Attention"}, "保存しました: Attention"),
        (409, {"detail": "x"}, "2611.00001 は登録済みです"),
        (502, {"detail": "arXiv に繋がらないため登録できませんでした。しばらくしてからもう一度試してください"},
         "arXiv に繋がらないため登録できませんでした。しばらくしてからもう一度試してください"),
    ],
)
def test_save_message(monkeypatch, status, body, text):
    monkeypatch.setattr(bot.httpx, "post", lambda url, json, timeout, headers=None: httpx.Response(status, json=body, request=httpx.Request("POST", url)))
    assert bot.save_message("2611.00001", Logger()) == text


def test_save_message_records_saver(monkeypatch):
    # 保存した人をメモに残す
    patched = {}
    monkeypatch.setattr(bot.httpx, "post", lambda url, json, timeout, headers=None: httpx.Response(201, json={"id": 7, "title": "T"}, request=httpx.Request("POST", url)))

    def patch(url, json, timeout, headers=None):
        patched[url] = json
        return httpx.Response(200, json={}, request=httpx.Request("PATCH", url))

    monkeypatch.setattr(bot.httpx, "patch", patch)
    assert bot.save_message("2611.00001", Logger(), saver="ryousei") == "保存しました: T"
    assert patched == {f"{bot.API_URL}/papers/7": {"note": "— Slack の新着通知から @ryousei が保存"}}


def test_save_message_backend_down(monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(bot.httpx, "post", down)
    assert bot.save_message("2611.00001", Logger()) == "backend に接続できませんでした"


def test_save_button_is_registered():
    class App:
        def __init__(self):
            self.actions = {}

        def event(self, name):
            return lambda f: f

        def action(self, action_id):
            def deco(f):
                self.actions[action_id] = f
                return f
            return deco

    app = App()
    bot.register(app)
    assert "save_paper" in app.actions

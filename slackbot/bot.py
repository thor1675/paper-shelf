import html
import os
import re
import time

import httpx

API_URL = os.environ.get("API_URL", "http://backend:8000")
# arXiv API の利用規約で、リクエストは 3 秒に 1 回まで
ARXIV_INTERVAL = 3

_ID = r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?"
# arxiv.org/abs/… と arxiv.org/pdf/… の URL、それに "arXiv:2401.12345" の形を拾う。
# 数字だけ（2401.12345）は日付や番号と区別できないので拾わない
ARXIV_PATTERN = re.compile(rf"(?i:arxiv\.org)/(?:abs|pdf)/{_ID}|(?i:arxiv):\s*{_ID}")

REACTIONS = {201: "white_check_mark", 409: "eyes"}
REACTION_FAILED = "warning"


def extract_arxiv_ids(text: str) -> list[str]:
    """メッセージから arXiv ID を出現順・重複なしで取り出す"""
    ids: list[str] = []
    for m in ARXIV_PATTERN.finditer(text):
        arxiv_id = m.group(1) or m.group(2)
        if arxiv_id not in ids:
            ids.append(arxiv_id)
    return ids


def slack_to_markdown(text: str, user_name=lambda uid: uid) -> str:
    """Slack 独自の書式（<url|label>、<@U123> など）を普通の Markdown に直す"""

    def replace(m: re.Match) -> str:
        body = m.group(1)
        target, _, label = body.partition("|")
        if target.startswith("@"):
            return f"@{user_name(target[1:])}"
        if target.startswith("#"):
            return f"#{label or target[1:]}"
        if target.startswith("!"):
            return f"@{label or target[1:]}"
        return f"[{label}]({target})" if label else target

    return html.unescape(re.sub(r"<([^<>]+)>", replace, text))


def build_note(text: str, author: str, channel: str, permalink: str | None) -> str:
    quote = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
    source = f"— @{author} in #{channel}"
    if permalink:
        source += f"（[Slack で開く]({permalink})）"
    return f"{quote}\n\n{source}"


def register(app) -> None:
    @app.event("message")
    def on_message(event, client, logger):
        # 編集・削除・ボット自身の投稿などは無視する
        if event.get("subtype") not in (None, "thread_broadcast", "file_share"):
            return
        if event.get("bot_id"):
            return
        ids = extract_arxiv_ids(event.get("text", ""))
        if not ids:
            return

        channel_id, ts = event["channel"], event["ts"]
        note: str | None = None
        reactions: list[str] = []
        for i, arxiv_id in enumerate(ids):
            if i > 0:
                time.sleep(ARXIV_INTERVAL)
            try:
                res = httpx.post(f"{API_URL}/papers", json={"arxiv_id": arxiv_id}, timeout=30)
                if res.status_code == 201:
                    # 投稿文をメモに残す（新しく登録したときだけ）
                    note = note or _note_for(event, client, logger)
                    httpx.patch(
                        f"{API_URL}/papers/{res.json()['id']}", json={"note": note}, timeout=10
                    ).raise_for_status()
                elif res.status_code != 409:
                    logger.warning("登録に失敗 %s: %s %s", arxiv_id, res.status_code, res.text)
                reaction = REACTIONS.get(res.status_code, REACTION_FAILED)
            except httpx.HTTPError as e:
                logger.warning("backend に接続できません %s: %s", arxiv_id, e)
                reaction = REACTION_FAILED
            if reaction not in reactions:
                reactions.append(reaction)

        for name in reactions:
            try:
                client.reactions_add(channel=channel_id, timestamp=ts, name=name)
            except Exception as e:  # すでに付いている場合など。保存には影響しないので無視
                logger.info("リアクションを付けられませんでした: %s", e)


def _note_for(event, client, logger) -> str:
    def user_name(uid: str) -> str:
        try:
            profile = client.users_info(user=uid)["user"]["profile"]
            return profile.get("display_name") or profile.get("real_name") or uid
        except Exception:
            return uid

    try:
        channel = client.conversations_info(channel=event["channel"])["channel"]["name"]
    except Exception:
        channel = event["channel"]
    try:
        permalink = client.chat_getPermalink(
            channel=event["channel"], message_ts=event["ts"]
        )["permalink"]
    except Exception as e:
        logger.info("permalink を取得できませんでした: %s", e)
        permalink = None

    text = slack_to_markdown(event.get("text", ""), user_name)
    return build_note(text, user_name(event.get("user", "")), channel, permalink)


def main() -> None:
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not bot_token or not app_token:
        print("SLACK_BOT_TOKEN と SLACK_APP_TOKEN が .env に無いので、slackbot は起動しません")
        return

    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = App(token=bot_token)
    register(app)
    print(f"slackbot を起動します（backend: {API_URL}）")
    SocketModeHandler(app, app_token).start()


if __name__ == "__main__":
    main()

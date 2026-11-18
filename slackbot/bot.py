import html
import logging
import os
import re
import sys

import httpx

API_URL = os.environ.get("API_URL", "http://backend:8000")
# arXiv の「3 秒に 1 回」は backend がまとめて守るので、ここでは待たない
# 登録は backend 側で arXiv の空きを待つことがあるので、長めに待つ
POST_TIMEOUT = 60

# 後ろに数字が続くもの（2401.123456 の先頭 5 桁など）は ID として拾わない
_ID = r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?(?!\d)"
# arxiv.org/abs|pdf|html/… の URL（fooarxiv.org は除く）と、"arXiv:2401.12345" の形を拾う。
# 数字だけ（2401.12345）は日付や番号と区別できないので拾わない
ARXIV_PATTERN = re.compile(
    rf"(?<![\w-])(?i:arxiv\.org)/(?:abs|pdf|html)/{_ID}|\b(?i:arxiv):\s*{_ID}"
)

REACTIONS = {201: "white_check_mark", 409: "eyes"}
REACTION_FAILED = "warning"

# backend との合言葉。backend はこれと操作した人の Slack ID を見て、紐づけた人の本棚に入れる
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# PAPER - Shelf の設定画面で出す、Slack との紐づけのコード
LINK_PATTERN = re.compile(r"\bps-link-[2-9A-HJ-NP-Z]{8}\b")


def api_headers(slack_user: str) -> dict[str, str]:
    """slackbot が backend を呼ぶときのヘッダー。slack_user はその操作をした人の Slack ID"""
    return {"X-Bot-Token": BOT_TOKEN, "X-Slack-User": slack_user}


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
            # <!here> → @here。<!subteam^S1|@team> や <!date^…|2月18日> はラベルをそのまま使う
            return label or f"@{target[1:]}"
        if label:
            # ラベルに [ ] があると Markdown のリンクが壊れるのでエスケープする
            label = label.replace("[", "\\[").replace("]", "\\]")
            return f"[{label}]({target})"
        return target

    return html.unescape(re.sub(r"<([^<>]+)>", replace, text))


def build_note(text: str, author: str, channel: str, permalink: str | None) -> str:
    quote = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
    source = f"— #{channel} で @{author} が投稿"
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
        channel_id, ts, user = event["channel"], event["ts"], event.get("user", "")

        # 設定画面で出した紐づけのコードが貼られたら、投稿した人の Slack アカウントを紐づける
        link = LINK_PATTERN.search(event.get("text", ""))
        if link:
            _ephemeral(client, channel_id, user, link_message(link.group(0), user, logger), logger)
            return

        ids = extract_arxiv_ids(event.get("text", ""))
        if not ids:
            return

        note: str | None = None
        reactions: list[str] = []
        for arxiv_id in ids:
            try:
                res = httpx.post(
                    f"{API_URL}/papers", json={"arxiv_id": arxiv_id}, headers=api_headers(user), timeout=POST_TIMEOUT
                )
                if res.status_code in (401, 403):
                    # 紐づけていない人の投稿は保存しない。リアクションは付けず、投稿した人にだけ伝える
                    _ephemeral(client, channel_id, user, _detail(res), logger)
                    return
                if res.status_code == 201:
                    # 投稿文をメモに残す（新しく登録したときだけ）。
                    # 失敗しても論文の保存はできているので、✅ のままにしてログだけ残す
                    note = note or _note_for(event, client, logger)
                    try:
                        httpx.patch(
                            f"{API_URL}/papers/{res.json()['id']}",
                            json={"note": note},
                            headers=api_headers(user),
                            timeout=10,
                        ).raise_for_status()
                    except httpx.HTTPError as e:
                        logger.warning("メモを書き込めませんでした %s: %s", arxiv_id, e)
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

    @app.action("save_paper")
    def on_save(ack, body, client, respond, logger):
        """
        新着の投稿の「保存」ボタン。保存できたら誰が保存したかを通知のスレッドに書き（全員に見える）、
        メモにも残す。登録済みや失敗は押した人にだけ見える返事で伝える
        """
        ack()
        arxiv_id = body["actions"][0]["value"]
        user = body.get("user", {})
        saver = user.get("username") or user.get("name") or user.get("id", "")
        text = save_message(arxiv_id, logger, slack_user=user.get("id", ""), saver=saver)
        if text.startswith("保存しました") and body.get("container", {}).get("message_ts"):
            try:
                client.chat_postMessage(
                    channel=body["container"]["channel_id"],
                    thread_ts=body["container"]["message_ts"],
                    text=f"<@{user.get('id')}> が{text}",
                    unfurl_links=False,
                )
                return
            except Exception as e:  # スレッドに書けなくても保存はできているので、押した人にだけ伝える
                logger.info("スレッドに書き込めませんでした: %s", e)
        respond(response_type="ephemeral", replace_original=False, text=text)


def _detail(res: httpx.Response) -> str:
    try:
        return res.json()["detail"]
    except (ValueError, KeyError):
        return f"保存できませんでした（{res.status_code}）"


def _ephemeral(client, channel: str, user: str, text: str, logger) -> None:
    """その人にだけ見える返事"""
    try:
        client.chat_postEphemeral(channel=channel, user=user, text=text)
    except Exception as e:
        logger.info("返事を送れませんでした: %s", e)


def link_message(code: str, slack_user: str, logger) -> str:
    """紐づけのコードを backend に送り、結果の文を返す"""
    try:
        res = httpx.post(
            f"{API_URL}/bot/slack-link",
            json={"code": code, "slack_user_id": slack_user},
            headers=api_headers(slack_user),
            timeout=10,
        )
    except httpx.HTTPError as e:
        logger.warning("backend に接続できません: %s", e)
        return "backend に接続できませんでした"
    if res.status_code == 200:
        return f"PAPER - Shelf の「{res.json()['username']}」と紐づけました。リンクを貼ると、あなたの本棚に保存されます"
    return _detail(res)


def save_message(arxiv_id: str, logger, slack_user: str = "", saver: str | None = None) -> str:
    """
    「保存」ボタンが押されたときに、押した人（slack_user）の本棚に登録し、結果の文を返す。
    saver があれば、誰が保存したかをメモに残す
    """
    headers = api_headers(slack_user)
    try:
        res = httpx.post(f"{API_URL}/papers", json={"arxiv_id": arxiv_id}, headers=headers, timeout=POST_TIMEOUT)
    except httpx.HTTPError as e:
        logger.warning("backend に接続できません %s: %s", arxiv_id, e)
        return "backend に接続できませんでした"
    if res.status_code == 201:
        if saver:
            try:
                httpx.patch(
                    f"{API_URL}/papers/{res.json()['id']}",
                    json={"note": f"— Slack の新着通知から @{saver} が保存"},
                    headers=headers,
                    timeout=10,
                ).raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("メモを書き込めませんでした %s: %s", arxiv_id, e)
        return f"保存しました: {res.json()['title']}"
    if res.status_code == 409:
        return f"{arxiv_id} は登録済みです"
    return _detail(res)


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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    channel = os.environ.get("SLACK_NOTIFY_CHANNEL")
    hour = int(os.environ.get("NOTIFY_HOUR") or 9)
    if not bot_token or not app_token:
        print("SLACK_BOT_TOKEN と SLACK_APP_TOKEN が .env に無いので、slackbot は起動しません")
        return

    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    import notify

    app = App(token=bot_token)

    # python bot.py notify … 9 時を待たずに、新着の通知を 1 回だけ動かす（試すとき用）
    if sys.argv[1:] == ["notify"]:
        if not channel:
            print("SLACK_NOTIFY_CHANNEL が .env に無いので、新着を知らせられません")
            return
        print(f"新着を {notify.notify_all(app.client, channel)} 本知らせました")
        return

    register(app)
    if channel:
        notify.start_scheduler(app.client, channel, hour)
        print(f"毎日 {hour} 時に新着を知らせます（チャンネル: {channel}）")
    else:
        print("SLACK_NOTIFY_CHANNEL が .env に無いので、新着の通知はしません")
    print(f"slackbot を起動します（backend: {API_URL}）")
    SocketModeHandler(app, app_token).start()


if __name__ == "__main__":
    main()

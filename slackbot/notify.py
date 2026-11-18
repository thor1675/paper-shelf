"""毎朝、登録したキーワードの arXiv の新着を Slack に流す"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from bot import BOT_TOKEN, api_headers

API_URL = os.environ.get("API_URL", "http://backend:8000")
JST = timezone(timedelta(hours=9))
# 1 つの投稿に載せる上限。Slack の 1 投稿のブロック数（50）に収める
MAX_ITEMS = 20

logger = logging.getLogger(__name__)


def _escape(s: str) -> str:
    # Slack の mrkdwn で特別な意味を持つ文字
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_blocks(query: str, items: list[dict], slack_user: str | None = None) -> list[dict]:
    """
    新着 1 本ずつに「保存」ボタンを付けた Slack の投稿。slack_user はキーワードを登録した人（メンションする）。
    「保存」は押した人の本棚に入る
    """
    shown = items[:MAX_ITEMS]
    mention = f"<@{slack_user}> " if slack_user else ""
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{mention}*「{_escape(query)}」の新着 {len(items)} 本*"}}
    ]
    for p in shown:
        authors = ", ".join(p["authors"][:3]) + (f" 他{len(p['authors']) - 3}人" if len(p["authors"]) > 3 else "")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{p['arxiv_url']}|{_escape(p['title'])}>\n{_escape(authors)} · {p['published']}",
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "保存"},
                    "action_id": "save_paper",
                    "value": p["arxiv_id"],
                },
            }
        )
    if len(items) > len(shown):
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"ほか {len(items) - len(shown)} 本はアプリの「新着」で見られます"}]}
        )
    return blocks


def notify_all(client, channel: str) -> int:
    """
    キーワードごとに新着を調べて投稿し、知らせた ID を backend に記録する。投稿した本数を返す。
    キーワードは人ごとで、Slack を紐づけた人の分だけ調べる（新着の判定もその人の本棚で行う）。
    1 つのキーワードで失敗しても、他のキーワードは続ける
    """
    try:
        watches = httpx.get(f"{API_URL}/bot/watches", headers={"X-Bot-Token": BOT_TOKEN}, timeout=10).raise_for_status().json()
    except httpx.HTTPError as e:
        logger.warning("キーワードを取得できませんでした: %s", e)
        return 0

    posted = 0
    for w in watches:
        headers = api_headers(w["slack_user_id"])
        try:
            # 新着の取得は arXiv への問い合わせを含むので長めに待つ
            items = httpx.get(f"{API_URL}/watches/{w['id']}/new", headers=headers, timeout=60).raise_for_status().json()
        except httpx.HTTPError as e:
            logger.warning("「%s」の新着を取得できませんでした: %s", w["query"], e)
            continue
        if not items:
            continue
        try:
            client.chat_postMessage(
                channel=channel,
                text=f"「{w['query']}」の新着 {len(items)} 本",  # 通知やブロックを表示できない環境向け
                blocks=build_blocks(w["query"], items, w["slack_user_id"]),
                unfurl_links=False,
            )
        except Exception as e:
            logger.warning("「%s」の新着を投稿できませんでした: %s", w["query"], e)
            continue
        # 投稿できたものだけ「知らせた」として記録する（投稿に失敗したら次の日にまた出る）
        shown = [p["arxiv_id"] for p in items[:MAX_ITEMS]]
        try:
            httpx.post(
                f"{API_URL}/watches/{w['id']}/seen", json={"arxiv_ids": shown}, headers=headers, timeout=10
            ).raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("「%s」の通知済みを記録できませんでした: %s", w["query"], e)
        posted += len(shown)
    return posted


def seconds_until(hour: int, now: datetime) -> float:
    """now から、次の日本時間 hour 時 0 分までの秒数"""
    now = now.astimezone(JST)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def start_scheduler(client, channel: str, hour: int) -> threading.Thread:
    """毎日 hour 時に notify_all を動かすスレッドを立てる"""

    def loop():
        while True:
            time.sleep(seconds_until(hour, datetime.now(JST)))
            logger.info("新着を調べます")
            n = notify_all(client, channel)
            logger.info("新着を %s 本知らせました", n)

    thread = threading.Thread(target=loop, name="notify", daemon=True)
    thread.start()
    return thread

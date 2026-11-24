"""
どこで動かすかで変わる設定（手元の Docker と、公開版の Render / Vercel で値を変える）。
"""

import os
from urllib.parse import urlparse

# 画面（Next.js）の URL。CORS の許可先、訳文を埋め込める親画面、GitHub ログイン後の戻り先に使う
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
# ブラウザから見た API の URL。公開版では Vercel の /api を通すので https://<frontend>/api になる。
# GitHub に登録する戻り先（Redirect URI）はこれ + /auth/github/callback
PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
# API の Cookie が届くパスの頭（/api を通すなら /api）
API_PATH_PREFIX = urlparse(PUBLIC_API_URL).path.rstrip("/")
# https で公開しているときは Cookie に Secure を付ける（http の通信では送られなくなる）
COOKIE_SECURE = FRONTEND_URL.startswith("https://")
# 翻訳サーバー。空なら翻訳は使えない（無料のサーバーには FuguMT が載らないため、公開版では空にする）
TRANSLATOR_URL = os.environ.get("TRANSLATOR_URL", "http://translator:8001").rstrip("/")

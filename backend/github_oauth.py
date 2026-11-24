"""
GitHub の OAuth2（認可コードフロー + PKCE）でのログインと、GitHub アカウントの紐づけ。

流れ:
1. 画面の「GitHub でログイン」/「GitHub と紐づける」が GET /auth/github/start に移る
2. ここで state（なりすまし防止の使い捨ての値）と PKCE の code_verifier を作り、HttpOnly の Cookie に入れて
   GitHub の認可画面へリダイレクトする（code_challenge = SHA-256(code_verifier) だけを GitHub に渡す）
3. 利用者が GitHub で許可すると、GitHub が GET /auth/github/callback?code=...&state=... に戻す
4. state が Cookie のものと一致するかを確かめ、code と code_verifier と client_secret でアクセストークンに交換する
5. アクセストークンで GitHub の利用者情報（id と login）を取り、紐づけた PAPER - Shelf の利用者としてログインさせる

アクセストークンは利用者を確かめるのに 1 回使うだけで、保存しない。scope は指定しない（公開情報だけ読める）。
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from config import API_PATH_PREFIX, COOKIE_SECURE, FRONTEND_URL, PUBLIC_API_URL
from auth import _start_session, browser_user, current_user
from db import get_session
from models import User

GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"

STATE_COOKIE = "ps_oauth"
STATE_MINUTES = 10
STATE_PATH = f"{API_PATH_PREFIX}/auth/github"

router = APIRouter(tags=["auth"])


def enabled() -> bool:
    return bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)


def _redirect_uri() -> str:
    return f"{PUBLIC_API_URL}/auth/github/callback"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _safe_next(next_path: str | None) -> str:
    # ほかのサイトへ移されないよう、アプリの中のパスだけを受け付ける
    return next_path if next_path and next_path.startswith("/") and not next_path.startswith("//") else "/"


def _back(path: str, **params: str) -> RedirectResponse:
    """画面（frontend）に戻す。エラーは ?github_error= で伝え、画面が日本語にする"""
    query = f"?{urlencode(params)}" if params else ""
    res = RedirectResponse(f"{FRONTEND_URL}{path}{query}", status_code=303)
    res.delete_cookie(STATE_COOKIE, path=STATE_PATH, secure=COOKIE_SECURE, httponly=True, samesite="lax")
    return res


# --- GitHub との通信（テストでは差し替える） ---


def exchange_code(code: str, verifier: str) -> str:
    """認可コードをアクセストークンに交換する"""
    res = httpx.post(
        TOKEN_URL,
        data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": _redirect_uri(),
            "code_verifier": verifier,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    res.raise_for_status()
    token = res.json().get("access_token")
    if not token:
        # 期限切れや使用済みのコードでは、200 で {"error": "bad_verification_code"} が返る
        raise ValueError(res.json().get("error", "no access_token"))
    return token


def fetch_github_user(token: str) -> tuple[int, str]:
    res = httpx.get(
        USER_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    res.raise_for_status()
    data = res.json()
    return int(data["id"]), str(data["login"])


# --- エンドポイント ---


@router.get("/auth/github/start")
def github_start(request: Request, mode: str = "login", next: str | None = None, session: Session = Depends(get_session)):
    if not enabled():
        raise HTTPException(404, "GitHub でのログインは設定されていません")
    if mode not in ("login", "link"):
        raise HTTPException(422, "「mode」は login か link にしてください")
    if mode == "link":
        # 紐づけはログイン中の人だけ（ログインしていなければ 401）
        current_user(request, None, None, session)
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "state": state,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "allow_signup": "false",
    }
    res = RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}", status_code=303)
    value = json.dumps({"state": state, "verifier": verifier, "mode": mode, "next": _safe_next(next)})
    # GitHub から戻ってくるのはトップレベルの GET なので、SameSite=Lax でも送られる
    res.set_cookie(
        STATE_COOKIE,
        base64.urlsafe_b64encode(value.encode()).decode(),
        max_age=STATE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path=STATE_PATH,
    )
    return res


@router.get("/auth/github/callback")
def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
):
    try:
        saved = json.loads(base64.urlsafe_b64decode(request.cookies.get(STATE_COOKIE, "")))
    except ValueError:
        saved = None
    mode = saved.get("mode") if isinstance(saved, dict) else None
    fail_path = "/settings" if mode == "link" else "/login"
    if error:
        # 利用者が GitHub の画面で「キャンセル」を押した（error=access_denied）など
        return _back(fail_path, github_error="denied")
    if not isinstance(saved, dict) or not state or not code or not hmac.compare_digest(state, str(saved.get("state", ""))):
        return _back(fail_path, github_error="state")
    try:
        github_id, github_login = fetch_github_user(exchange_code(code, str(saved["verifier"])))
    except (httpx.HTTPError, ValueError, KeyError):
        return _back(fail_path, github_error="github")

    owner = session.exec(select(User).where(User.github_id == github_id)).first()
    if mode == "link":
        try:
            user = current_user(request, None, None, session)
        except HTTPException:
            return _back("/login", github_error="login_required")
        if owner and owner.id != user.id:
            return _back("/settings", github_error="taken")
        user.github_id, user.github_login = github_id, github_login
        session.add(user)
        session.commit()
        return _back("/settings", github="linked")

    if not owner:
        return _back("/login", github_error="not_linked")
    # GitHub で名前を変えていたら追いかける
    if owner.github_login != github_login:
        owner.github_login = github_login
        session.add(owner)
        session.commit()
    res = _back(_safe_next(saved.get("next")))
    _start_session(session, res, owner)
    return res


@router.delete("/auth/github-link", status_code=204)
def unlink_github(user: User = Depends(browser_user), session: Session = Depends(get_session)):
    user.github_id = None
    user.github_login = None
    session.add(user)
    session.commit()
    return Response(status_code=204)


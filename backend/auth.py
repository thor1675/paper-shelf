"""
ログイン（ユーザー名とパスワード）と、Slack との紐づけ。

- パスワードは scrypt（Python 標準）でハッシュにして保存する
- ログイン中かどうかは Cookie（ps_session）で見る。DB には Cookie の値の SHA-256 だけを保存する
- 最初の 1 人は招待コード無しで登録でき、ログインを付ける前の論文とキーワードを引き継ぐ。2 人目からは招待コードが要る
- slackbot は BOT_TOKEN と、操作した人の Slack ID（X-Slack-User）を送る。紐づけた人として扱う
"""

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import update
from sqlmodel import Session, col, select

from db import get_session
from models import (
    BotWatch,
    CodeRead,
    Invite,
    LoginBody,
    Me,
    PasswordBody,
    RegisterBody,
    SetupState,
    ShelfEntry,
    SlackLinkBody,
    SlackLinkCode,
    User,
    UserSession,
    UsernameBody,
    Watch,
)

COOKIE = "ps_session"
SESSION_DAYS = 30
INVITE_DAYS = 7
LINK_MINUTES = 10
# slackbot との合言葉。空なら slackbot からの操作は受け付けない
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

LOGIN_REQUIRED = "ログインしてください"
NOT_LINKED = "Slack アカウントが PAPER - Shelf に紐づいていません。PAPER - Shelf の設定画面から紐づけてください"

router = APIRouter(tags=["auth"])


# --- パスワード ---

# scrypt の強さ。1 回のハッシュに 16 MB と数十ミリ秒かかる
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p))
    except ValueError:
        return False
    return hmac.compare_digest(got, base64.b64decode(digest))


# ユーザーがいないときも同じだけ時間をかけ、ユーザー名が存在するかを応答時間で分からないようにする
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# --- ログイン中かどうか ---


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _code(prefix: str = "") -> str:
    # 読み間違えやすい 0 O 1 I を除いた 8 文字
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return prefix + "".join(secrets.choice(alphabet) for _ in range(8))


def current_user(
    request: Request,
    x_bot_token: str | None = Header(default=None),
    x_slack_user: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """ログイン中の人。slackbot からなら、紐づけた Slack アカウントの人"""
    if x_bot_token is not None:
        if not BOT_TOKEN or not hmac.compare_digest(x_bot_token, BOT_TOKEN):
            raise HTTPException(401, "slackbot の合言葉（BOT_TOKEN）が違います")
        user = session.exec(select(User).where(User.slack_user_id == x_slack_user)).first() if x_slack_user else None
        if not user:
            raise HTTPException(403, NOT_LINKED)
        return user
    token = request.cookies.get(COOKIE)
    if token:
        s = session.get(UserSession, _hash_token(token))
        if s and s.expires_at > _now():
            user = session.get(User, s.user_id)
            if user:
                return user
    raise HTTPException(401, LOGIN_REQUIRED)


def require_bot(x_bot_token: str | None = Header(default=None)) -> None:
    if not BOT_TOKEN or not x_bot_token or not hmac.compare_digest(x_bot_token, BOT_TOKEN):
        raise HTTPException(401, "slackbot の合言葉（BOT_TOKEN）が違います")


def _start_session(session: Session, response: Response, user: User) -> None:
    token = secrets.token_urlsafe(32)
    session.add(UserSession(token_hash=_hash_token(token), user_id=user.id, expires_at=_now() + timedelta(days=SESSION_DAYS)))
    session.commit()
    # HttpOnly: 画面のスクリプトから読めないようにする。SameSite=Lax: ほかのサイトからの POST では送られない
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/")


def _me(user: User) -> Me:
    return Me(id=user.id, username=user.username, slack_linked=user.slack_user_id is not None, github_login=user.github_login)


# --- 登録・ログイン・ログアウト ---


@router.get("/auth/setup", response_model=SetupState)
def setup_state(session: Session = Depends(get_session)):
    import github_oauth

    return SetupState(needs_setup=session.exec(select(User.id)).first() is None, github_enabled=github_oauth.enabled())


@router.post("/auth/register", response_model=Me, status_code=201)
def register(body: RegisterBody, response: Response, session: Session = Depends(get_session)):
    first = session.exec(select(User.id)).first() is None
    invite = None
    if not first:
        invite = session.get(Invite, (body.invite_code or "").strip().upper())
        if not invite or invite.used_by is not None or invite.expires_at < _now():
            raise HTTPException(403, "招待コードが正しくないか、期限が切れています")
    if session.exec(select(User).where(User.username == body.username)).first():
        raise HTTPException(409, f"ユーザー名「{body.username}」は使われています")
    user = User(username=body.username, password_hash=hash_password(body.password))
    session.add(user)
    session.flush()
    if invite:
        invite.used_by = user.id
        session.add(invite)
    if first:
        # ログインを付ける前の論文とキーワードは、最初の 1 人のものにする
        session.exec(update(ShelfEntry).where(col(ShelfEntry.user_id).is_(None)).values(user_id=user.id))
        session.exec(update(Watch).where(col(Watch.user_id).is_(None)).values(user_id=user.id))
    session.commit()
    session.refresh(user)
    _start_session(session, response, user)
    return _me(user)


@router.post("/auth/login", response_model=Me)
def login(body: LoginBody, response: Response, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == body.username)).first()
    if not verify_password(body.password, user.password_hash if user else _DUMMY_HASH) or not user:
        raise HTTPException(401, "ユーザー名かパスワードが違います")
    _start_session(session, response, user)
    return _me(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, session: Session = Depends(get_session)):
    token = request.cookies.get(COOKIE)
    if token and (s := session.get(UserSession, _hash_token(token))):
        session.delete(s)
        session.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/auth/me", response_model=Me)
def me(user: User = Depends(current_user)):
    return _me(user)


# --- ユーザー名・パスワードの変更 ---

WRONG_PASSWORD = "今のパスワードが違います"


def browser_user(request: Request, user: User = Depends(current_user)) -> User:
    """画面からログインしている人。slackbot からはユーザー名やパスワードを変えられない"""
    if request.headers.get("x-bot-token") is not None:
        raise HTTPException(403, "Slack からは変更できません")
    return user


def _check_current(user: User, password: str) -> None:
    # 401 にすると画面がログイン画面に移ってしまうので 403
    if not verify_password(password, user.password_hash):
        raise HTTPException(403, WRONG_PASSWORD)


@router.patch("/auth/username", response_model=Me)
def change_username(body: UsernameBody, user: User = Depends(browser_user), session: Session = Depends(get_session)):
    _check_current(user, body.current_password)
    if body.username != user.username:
        if session.exec(select(User).where(User.username == body.username)).first():
            raise HTTPException(409, f"ユーザー名「{body.username}」は使われています")
        user.username = body.username
        session.add(user)
        session.commit()
        session.refresh(user)
    return _me(user)


@router.post("/auth/password", status_code=204)
def change_password(
    body: PasswordBody, request: Request, user: User = Depends(browser_user), session: Session = Depends(get_session)
):
    _check_current(user, body.current_password)
    user.password_hash = hash_password(body.new_password)
    session.add(user)
    # ほかの端末のログインは切る（今使っている端末はそのまま）
    keep = _hash_token(request.cookies.get(COOKIE, ""))
    for s in session.exec(select(UserSession).where(UserSession.user_id == user.id, UserSession.token_hash != keep)).all():
        session.delete(s)
    session.commit()
    return Response(status_code=204)


# --- 招待コード ---


@router.post("/auth/invites", response_model=CodeRead, status_code=201)
def create_invite(user: User = Depends(current_user), session: Session = Depends(get_session)):
    invite = Invite(code=_code(), created_by=user.id, expires_at=_now() + timedelta(days=INVITE_DAYS))
    session.add(invite)
    session.commit()
    return CodeRead(code=invite.code, expires_at=invite.expires_at)


@router.get("/auth/invites", response_model=list[CodeRead])
def list_invites(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """自分が作った、まだ使われていない期限内の招待コード"""
    rows = session.exec(
        select(Invite)
        .where(Invite.created_by == user.id, col(Invite.used_by).is_(None), Invite.expires_at > _now())
        .order_by(col(Invite.created_at))
    ).all()
    return [CodeRead(code=i.code, expires_at=i.expires_at) for i in rows]


# --- Slack との紐づけ ---


@router.post("/auth/slack-link-code", response_model=CodeRead, status_code=201)
def create_slack_link_code(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Slack に投稿してもらうコード。投稿した人の Slack アカウントが、この人に紐づく"""
    for old in session.exec(select(SlackLinkCode).where(SlackLinkCode.user_id == user.id)).all():
        session.delete(old)
    link = SlackLinkCode(code=_code("ps-link-"), user_id=user.id, expires_at=_now() + timedelta(minutes=LINK_MINUTES))
    session.add(link)
    session.commit()
    return CodeRead(code=link.code, expires_at=link.expires_at)


@router.delete("/auth/slack-link", status_code=204)
def unlink_slack(user: User = Depends(current_user), session: Session = Depends(get_session)):
    user.slack_user_id = None
    session.add(user)
    session.commit()
    return Response(status_code=204)


@router.post("/bot/slack-link", response_model=Me, dependencies=[Depends(require_bot)])
def bot_slack_link(body: SlackLinkBody, session: Session = Depends(get_session)):
    """slackbot が、紐づけのコードを投稿した人の Slack ID と一緒に呼ぶ"""
    link = session.get(SlackLinkCode, body.code.strip())
    if not link or link.expires_at < _now():
        raise HTTPException(404, "紐づけのコードが正しくないか、期限が切れています。設定画面でもう一度コードを出してください")
    other = session.exec(select(User).where(User.slack_user_id == body.slack_user_id)).first()
    if other and other.id != link.user_id:
        raise HTTPException(409, f"この Slack アカウントは、すでに「{other.username}」に紐づいています")
    user = session.get(User, link.user_id)
    user.slack_user_id = body.slack_user_id
    session.add(user)
    session.delete(link)
    session.commit()
    session.refresh(user)
    return _me(user)


@router.get("/bot/watches", response_model=list[BotWatch], dependencies=[Depends(require_bot)])
def bot_watches(session: Session = Depends(get_session)):
    """新着を調べるキーワード。Slack を紐づけた人の分だけ（知らせる相手が分かるもの）"""
    rows = session.exec(
        select(Watch, User.slack_user_id)
        .join(User, col(User.id) == col(Watch.user_id))
        .where(col(User.slack_user_id).is_not(None))
        .order_by(col(Watch.id))
    ).all()
    return [BotWatch(id=w.id, query=w.query, slack_user_id=slack_id) for w, slack_id in rows]

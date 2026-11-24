"""GitHub の OAuth2 でのログインと紐づけ（GitHub との通信は偽物に差し替える）"""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import github_oauth
import main


@pytest.fixture
def github(monkeypatch):
    monkeypatch.setattr(github_oauth, "GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setattr(github_oauth, "GITHUB_CLIENT_SECRET", "client-secret")
    calls = {}

    def exchange(code, verifier):
        calls["code"], calls["verifier"] = code, verifier
        if code != "good-code":
            raise ValueError("bad_verification_code")
        return "gho_token"

    monkeypatch.setattr(github_oauth, "exchange_code", exchange)
    monkeypatch.setattr(github_oauth, "fetch_github_user", lambda token: (4242, "octo-alice"))
    return calls


def start(c, mode="login", next_path="/tags"):
    res = c.get("/auth/github/start", params={"mode": mode, "next": next_path}, follow_redirects=False)
    assert res.status_code == 303, res.text
    return res, parse_qs(urlparse(res.headers["location"]).query)


def callback(c, state, code="good-code"):
    return c.get("/auth/github/callback", params={"code": code, "state": state}, follow_redirects=False)


def test_disabled_without_client_id(client, monkeypatch):
    monkeypatch.setattr(github_oauth, "GITHUB_CLIENT_ID", "")
    monkeypatch.setattr(github_oauth, "GITHUB_CLIENT_SECRET", "")
    assert TestClient(main.app).get("/auth/setup").json()["github_enabled"] is False
    assert client.get("/auth/github/start", follow_redirects=False).status_code == 404


def test_start_redirects_with_pkce(client, github):
    assert TestClient(main.app).get("/auth/setup").json()["github_enabled"] is True
    res, q = start(TestClient(main.app))
    assert res.headers["location"].startswith("https://github.com/login/oauth/authorize?")
    assert q["client_id"] == ["client-id"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://localhost:8000/auth/github/callback"]
    # client_secret は URL に出さない。code_verifier は Cookie にだけ入れ、GitHub には SHA-256 だけを渡す
    assert "client-secret" not in res.headers["location"]
    cookie = res.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "Path=/auth/github" in cookie
    saved = json.loads(base64.urlsafe_b64decode(cookie.split(";")[0].split("=", 1)[1]))
    assert saved["state"] == q["state"][0]
    digest = base64.urlsafe_b64encode(hashlib.sha256(saved["verifier"].encode()).digest()).rstrip(b"=").decode()
    assert q["code_challenge"] == [digest]


def test_link_then_login(client, github):
    # ログイン中の alice が設定画面から紐づける
    _, q = start(client, mode="link")
    res = callback(client, q["state"][0])
    assert res.headers["location"] == "http://localhost:3000/settings?github=linked"
    assert client.get("/auth/me").json()["github_login"] == "octo-alice"

    # 別のブラウザ（ログインしていない）から GitHub でログインすると alice になる
    anon = TestClient(main.app)
    _, q = start(anon, next_path="/tags")
    res = callback(anon, q["state"][0])
    assert res.status_code == 303 and res.headers["location"] == "http://localhost:3000/tags"
    assert github["verifier"]  # code_verifier も交換に使った
    assert anon.get("/auth/me").json()["username"] == "alice"


def test_login_without_link_is_rejected(client, github):
    anon = TestClient(main.app)
    _, q = start(anon)
    res = callback(anon, q["state"][0])
    assert res.headers["location"] == "http://localhost:3000/login?github_error=not_linked"
    assert anon.get("/auth/me").status_code == 401


def test_state_must_match(client, github):
    anon = TestClient(main.app)
    start(anon)
    res = callback(anon, "forged-state")
    assert res.headers["location"].endswith("/login?github_error=state")
    # Cookie が無い（別のブラウザで始めた）ときも受け付けない
    _, q = start(TestClient(main.app))
    assert callback(TestClient(main.app), q["state"][0]).headers["location"].endswith("github_error=state")


def test_bad_code_and_cancel(client, github):
    anon = TestClient(main.app)
    _, q = start(anon)
    assert callback(anon, q["state"][0], code="expired").headers["location"].endswith("github_error=github")
    _, q = start(anon)
    res = anon.get("/auth/github/callback", params={"error": "access_denied", "state": q["state"][0]}, follow_redirects=False)
    assert res.headers["location"].endswith("/login?github_error=denied")


def test_github_account_cannot_be_linked_twice(client, other_client, github):
    _, q = start(client, mode="link")
    callback(client, q["state"][0])
    _, q = start(other_client, mode="link")
    assert callback(other_client, q["state"][0]).headers["location"].endswith("/settings?github_error=taken")


def test_link_requires_login_and_unlink(client, github):
    assert TestClient(main.app).get("/auth/github/start", params={"mode": "link"}, follow_redirects=False).status_code == 401
    _, q = start(client, mode="link")
    callback(client, q["state"][0])
    assert client.delete("/auth/github-link").status_code == 204
    assert client.get("/auth/me").json()["github_login"] is None
    anon = TestClient(main.app)
    _, q = start(anon)
    assert callback(anon, q["state"][0]).headers["location"].endswith("github_error=not_linked")


def test_next_cannot_leave_the_app(client, github):
    _, q = start(client, mode="link")
    callback(client, q["state"][0])
    anon = TestClient(main.app)
    _, q = start(anon, next_path="//evil.example")
    assert callback(anon, q["state"][0]).headers["location"] == "http://localhost:3000/"


def test_start_behind_vercel_proxy(client, github, monkeypatch):
    # 公開版: ブラウザは https://<画面>/api を通して API を呼ぶので、戻り先と Cookie のパスに /api が付く
    monkeypatch.setattr(github_oauth, "PUBLIC_API_URL", "https://shelf.example/api")
    monkeypatch.setattr(github_oauth, "STATE_PATH", "/api/auth/github")
    monkeypatch.setattr(github_oauth, "COOKIE_SECURE", True)
    res, q = start(TestClient(main.app))
    assert q["redirect_uri"] == ["https://shelf.example/api/auth/github/callback"]
    cookie = res.headers["set-cookie"]
    assert "Path=/api/auth/github" in cookie and "secure" in cookie.lower()

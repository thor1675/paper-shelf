import re
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import computed_field, field_validator, model_validator
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

Status = Literal["unread", "reading", "read"]

def normalize_tags(tags: list[str]) -> list[str]:
    """小文字にそろえ、前後の空白・空文字・重複を除く（順番は保つ）"""
    result: list[str] = []
    for t in tags:
        t = t.strip().lower()
        if t and t not in result:
            result.append(t)
    return result

# --- ユーザーとログイン ---

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, max_length=32)
    # scrypt のハッシュ（auth.py の hash_password）。パスワードそのものは保存しない
    password_hash: str = Field(max_length=256)
    # 紐づけた Slack のユーザー ID（U から始まる）。紐づけた人だけが Slack から保存できる
    slack_user_id: str | None = Field(default=None, unique=True, max_length=32)
    # 紐づけた GitHub アカウント（OAuth2 でログインできる）。id は変わらないが login（名前）は変えられるので id で引く
    github_id: int | None = Field(default=None, sa_column=Column(BigInteger, unique=True, nullable=True))
    github_login: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserSession(SQLModel, table=True):
    """ログイン中であることの記録。Cookie に入れる値そのものではなく、その SHA-256 を保存する"""

    __tablename__ = "user_sessions"

    token_hash: str = Field(primary_key=True, max_length=64)
    user_id: int = Field(sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

class Invite(SQLModel, table=True):
    """招待コード。2 人目からは、これが無いと登録できない。1 回使うと使えなくなる"""

    __tablename__ = "invites"

    code: str = Field(primary_key=True, max_length=32)
    created_by: int = Field(sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    used_by: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True))

class SlackLinkCode(SQLModel, table=True):
    """Slack との紐づけに使う一時的なコード。Slack に投稿すると、投稿した人の Slack アカウントが紐づく"""

    __tablename__ = "slack_link_codes"

    code: str = Field(primary_key=True, max_length=32)
    user_id: int = Field(sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False))
    expires_at: datetime

def check_username(v: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\-]{3,32}", v):
        raise ValueError("ユーザー名は半角英数字と _ - で 3〜32 文字にしてください")
    return v


def check_password(v: str) -> str:
    if not 8 <= len(v) <= 200:
        raise ValueError("パスワードは 8 文字以上にしてください")
    return v


class RegisterBody(SQLModel):
    model_config = {"extra": "forbid"}

    username: str
    password: str
    # 2 人目からは必須
    invite_code: str | None = None

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return check_username(v)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return check_password(v)

class UsernameBody(SQLModel):
    model_config = {"extra": "forbid"}

    username: str
    current_password: str

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return check_username(v)

class PasswordBody(SQLModel):
    model_config = {"extra": "forbid"}

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return check_password(v)

class LoginBody(SQLModel):
    model_config = {"extra": "forbid"}

    username: str
    password: str

class Me(SQLModel):
    id: int
    username: str
    slack_linked: bool
    github_login: str | None = None

class SetupState(SQLModel):
    # まだ誰も登録していない（最初の 1 人は招待コード無しで登録できる）
    needs_setup: bool
    # GitHub でログインできる（GITHUB_CLIENT_ID と GITHUB_CLIENT_SECRET が設定されている）
    github_enabled: bool = False

class CodeRead(SQLModel):
    code: str
    expires_at: datetime

class SlackLinkBody(SQLModel):
    model_config = {"extra": "forbid"}

    code: str
    slack_user_id: str = Field(min_length=1, max_length=32)

class BotWatch(SQLModel):
    """slackbot が新着を調べるためのキーワード。Slack を紐づけた人の分だけ"""

    id: int
    query: str
    slack_user_id: str

# --- 論文 ---

class Paper(SQLModel, table=True):
    """arXiv から取った論文の情報。全員で共有する（誰の本棚にあるかは ShelfEntry）"""

    __tablename__ = "papers"
    __table_args__ = (
        Index("ix_papers_authors", "authors", postgresql_using="gin"),
    )

    id: int | None = Field(default=None, primary_key=True)
    arxiv_id: str = Field(unique=True, index=True, max_length=32)
    title: str
    authors: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    abstract: str
    published: date

    # --- OpenAlex から取った引用の情報（POST /citations/sync で更新） ---
    openalex_id: str | None = Field(default=None, max_length=32, index=True)
    citation_count: int | None = None
    # この論文の参考文献（OpenAlex の ID）。references は SQL の予約語なので別の名前にした
    reference_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    scholar_synced_at: datetime | None = None

class ShelfEntry(SQLModel, table=True):
    """ある人の本棚に入っている 1 本。ステータス・タグ・メモ・読了日は人ごと"""

    __tablename__ = "shelf"
    __table_args__ = (
        CheckConstraint("status IN ('unread', 'reading', 'read')", name="ck_shelf_status"),
        UniqueConstraint("user_id", "paper_id", name="uq_shelf_user_paper"),
        Index("ix_shelf_tags", "tags", postgresql_using="gin"),
    )

    id: int | None = Field(default=None, primary_key=True)
    # ログインを付ける前の論文は、最初に登録した人のものにする（それまでは NULL）
    user_id: int | None = Field(
        default=None, sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    )
    paper_id: int = Field(sa_column=Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False))
    tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    note: str = Field(default="", sa_column_kwargs={"server_default": ""})
    status: str = Field(
        default="unread", max_length=16, sa_column_kwargs={"server_default": "unread"}
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # 「読了」にした日時。読了以外に戻したら消す
    read_at: datetime | None = None

class PaperCreate(SQLModel):
    model_config = {"extra": "forbid"}

    arxiv_id: str

class PaperUpdate(SQLModel):
    # 送られてきた項目だけ更新する。arXiv 由来のメタデータはここに含めない
    # extra="forbid": 定義に無い項目（title など）が来たら 422 にする
    model_config = {"extra": "forbid"}

    tags: list[str] | None = None
    note: str | None = None
    status: Status | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_null(cls, data):
        # {"note": null} を「変更なし」と黙って扱わず、422 にする（消したいときは "" や []）
        if isinstance(data, dict):
            nulls = [k for k, v in data.items() if v is None]
            if nulls:
                raise ValueError(f"null は使えません: {', '.join(nulls)}")
        return data

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else normalize_tags(v)

class PaperRead(SQLModel):
    id: int
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: date
    tags: list[str]
    note: str
    status: str
    created_at: datetime
    read_at: datetime | None
    openalex_id: str | None
    citation_count: int | None

    @computed_field
    @property
    def arxiv_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

    @computed_field
    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}"

    @classmethod
    def of(cls, paper: Paper, entry: ShelfEntry) -> "PaperRead":
        """共有の論文の情報と、その人の本棚の情報を合わせる"""
        # model_dump ではなく属性で読む（commit のあとの、まだ読み直していない行でも DB から読み直される）
        fields = {k: getattr(paper, k) for k in ("id", "arxiv_id", "title", "authors", "abstract", "published", "openalex_id", "citation_count")}
        fields |= {k: getattr(entry, k) for k in ("tags", "note", "status", "created_at", "read_at")}
        return cls(**fields)

class TagCount(SQLModel):
    name: str
    count: int

class YearCount(SQLModel):
    year: int
    count: int

class GraphNode(SQLModel):
    id: str
    count: int

class GraphEdge(SQLModel):
    source: str
    target: str
    weight: int

class Graph(SQLModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]

# --- まとめて登録 ---

class BatchCreate(SQLModel):
    model_config = {"extra": "forbid"}

    # 1 行 1 件の ID か URL。画面で改行・空白・カンマで分けてから送る
    items: list[str] = Field(min_length=1, max_length=50)

BatchStatus = Literal["created", "exists", "duplicate", "invalid", "not_found", "unavailable", "busy"]

class BatchItem(SQLModel):
    input: str
    arxiv_id: str | None
    result: BatchStatus
    paper_id: int | None = None
    title: str | None = None

# --- arXiv 検索 ---

class SearchItem(SQLModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: date
    # 登録済みなら、その論文の id
    paper_id: int | None

    @computed_field
    @property
    def arxiv_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

class SearchResult(SQLModel):
    total: int
    start: int
    items: list[SearchItem]

# --- 新着の通知 ---

class Watch(SQLModel, table=True):
    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("user_id", "query", name="uq_watches_user_query"),)

    id: int | None = Field(default=None, primary_key=True)
    # キーワードは人ごと。ログインを付ける前のものは、最初に登録した人のものにする
    user_id: int | None = Field(
        default=None, sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    )
    # arXiv の検索語（画面の検索と同じ書き方）
    query: str = Field(max_length=200)
    # 一度知らせた論文の ID。同じ論文を二度知らせないために使う
    seen: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notified_at: datetime | None = None

class WatchCreate(SQLModel):
    model_config = {"extra": "forbid"}

    query: str = Field(min_length=1, max_length=200)

class WatchRead(SQLModel):
    id: int
    query: str
    created_at: datetime
    notified_at: datetime | None

class WatchSeen(SQLModel):
    model_config = {"extra": "forbid"}

    arxiv_ids: list[str]

# --- 引用関係（OpenAlex） ---

class ScholarCache(SQLModel, table=True):
    """OpenAlex から取った結果を 7 日間とっておく（同じ論文を何度開いても速く、相手にも負担をかけない）"""

    __tablename__ = "scholar_cache"

    key: str = Field(primary_key=True, max_length=200)
    data: dict | list = Field(sa_column=Column(JSONB, nullable=False))
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CitationNode(SQLModel):
    work_id: str
    arxiv_id: str | None
    title: str
    year: int | None
    authors: list[str]
    cited_by_count: int
    # 登録済みなら、その論文の id
    paper_id: int | None = None

class CitationMap(SQLModel):
    center: CitationNode
    references: list[CitationNode]
    citations: list[CitationNode]
    references_total: int
    citations_total: int

class MissingItem(CitationNode):
    # この論文を参考文献に挙げている、登録済みの論文の id
    cited_by_papers: list[int]

class LibraryNode(SQLModel):
    paper_id: int
    title: str
    label: str
    year: int
    cited_by_count: int | None

class LibraryEdge(SQLModel):
    # source の論文が target の論文を引用している
    source: int
    target: int

class LibraryGraph(SQLModel):
    nodes: list[LibraryNode]
    edges: list[LibraryEdge]
    # まだ OpenAlex と同期していない論文の数
    unsynced: int

class SyncResult(SQLModel):
    synced: int
    not_found: int

class MonthCount(SQLModel):
    month: str
    count: int

class ReadStats(SQLModel):
    months: list[MonthCount]
    # 「読んだ」だが日時が分からない（記録を始める前に読んだ）論文の数
    unknown: int

# --- 一覧でまとめて操作・タグの管理 ---

class BulkUpdate(SQLModel):
    model_config = {"extra": "forbid"}

    ids: list[int] = Field(min_length=1, max_length=500)
    add_tags: list[str] = []
    remove_tags: list[str] = []
    status: Status | None = None
    # true なら選んだ論文を削除する（他の指定は無視）
    delete: bool = False

    @field_validator("add_tags", "remove_tags")
    @classmethod
    def _normalize(cls, v: list[str]) -> list[str]:
        return normalize_tags(v)

class BulkResult(SQLModel):
    updated: int
    deleted: int

class TagRename(SQLModel):
    model_config = {"extra": "forbid"}

    old: str = Field(min_length=1)
    # 既にあるタグの名前にすると、2 つのタグが 1 つにまとまる
    new: str = Field(min_length=1)

class TagChange(SQLModel):
    # 変わった論文の数
    papers: int

# --- 日本語で読む（翻訳） ---

TranslationState = Literal["queued", "running", "done", "failed"]

class Translation(SQLModel, table=True):
    """訳した HTML。1 本につき 1 行。自分で読むためだけにとっておく"""

    __tablename__ = "translations"

    arxiv_id: str = Field(primary_key=True, max_length=32)
    status: str = Field(default="queued", max_length=16)
    # 訳し終えた段落の数と、全体の段落の数（進み具合の表示に使う）
    done: int = 0
    total: int = 0
    # 取ってきた HTML 版の URL（arxiv.org/html か ar5iv）
    source_url: str | None = None
    html: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TranslationStatus(SQLModel):
    status: TranslationState | None
    done: int = 0
    total: int = 0
    source_url: str | None = None
    error: str | None = None

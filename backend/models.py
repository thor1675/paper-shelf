from datetime import date, datetime, timezone
from typing import Literal

from pydantic import computed_field, field_validator
from sqlalchemy import CheckConstraint, Column, Index, String
from sqlalchemy.dialects.postgresql import ARRAY
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

class Paper(SQLModel, table=True):
    __tablename__ = "papers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('unread', 'reading', 'read')", name="ck_papers_status"
        ),
        Index("ix_papers_tags", "tags", postgresql_using="gin"),
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
    tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    note: str = Field(default="", sa_column_kwargs={"server_default": ""})
    status: str = Field(
        default="unread", max_length=16, sa_column_kwargs={"server_default": "unread"}
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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

    @computed_field
    @property
    def arxiv_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

    @computed_field
    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}"

class TagCount(SQLModel):
    name: str
    count: int

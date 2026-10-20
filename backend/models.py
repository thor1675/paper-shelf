from datetime import date, datetime, timezone

from pydantic import computed_field
from sqlalchemy import CheckConstraint, Column, Index, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

STATUSES = ("unread", "reading", "read")

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
    arxiv_id: str

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

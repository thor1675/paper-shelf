from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import exists, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, or_, select

from arxiv import fetch_paper, is_valid_arxiv_id, normalize_arxiv_id
from db import get_session
from models import Paper, PaperCreate, PaperRead

app = FastAPI(title="paper-shelf API")


def like_pattern(s: str) -> str:
    """部分一致用。入力中の % と _ をワイルドカードとして扱わないようにする"""
    s = s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{s}%"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/papers", response_model=PaperRead, status_code=201)
def create_paper(body: PaperCreate, session: Session = Depends(get_session)):
    arxiv_id = normalize_arxiv_id(body.arxiv_id)
    if not is_valid_arxiv_id(arxiv_id):
        raise HTTPException(400, f"arXiv ID の形式ではありません: {body.arxiv_id}")

    # arXiv に問い合わせる前に二重登録を弾く
    if session.exec(select(Paper).where(Paper.arxiv_id == arxiv_id)).first():
        raise HTTPException(409, f"{arxiv_id} は登録済みです")

    try:
        data = fetch_paper(arxiv_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except httpx.HTTPError:
        raise HTTPException(502, "arXiv API に接続できませんでした")

    paper = Paper(**data)
    session.add(paper)
    try:
        session.commit()
    except IntegrityError:
        # 上のチェックと commit の間に同じ ID が登録された場合
        session.rollback()
        raise HTTPException(409, f"{arxiv_id} は登録済みです")
    session.refresh(paper)
    return paper


@app.get("/papers", response_model=list[PaperRead])
def list_papers(
    tag: list[str] = Query(default=[]),
    status: Literal["unread", "reading", "read"] | None = None,
    author: str | None = None,
    q: str | None = None,
    sort: Literal["created_at", "published"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    session: Session = Depends(get_session),
):
    stmt = select(Paper)
    tags = [t.strip().lower() for t in tag if t.strip()]
    if tags:
        # tags @> ARRAY[...]。指定したタグをすべて持つ論文（GIN インデックスが効く）
        stmt = stmt.where(col(Paper.tags).contains(tags))
    if status:
        stmt = stmt.where(Paper.status == status)
    if author:
        # 著者 1 人ずつに対して部分一致。EXISTS (SELECT * FROM unnest(authors) ...)
        name = func.unnest(Paper.authors).column_valued("name")
        stmt = stmt.where(exists().where(name.ilike(like_pattern(author), escape="\\")))
    if q:
        pattern = like_pattern(q)
        stmt = stmt.where(
            or_(
                col(Paper.title).ilike(pattern, escape="\\"),
                col(Paper.abstract).ilike(pattern, escape="\\"),
            )
        )
    sort_col = col(getattr(Paper, sort))
    stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
    return session.exec(stmt).all()


@app.get("/papers/{paper_id}", response_model=PaperRead)
def get_paper(paper_id: int, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "論文が見つかりません")
    return paper

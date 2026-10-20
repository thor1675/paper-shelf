from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import exists, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, or_, select

from arxiv import fetch_paper, is_valid_arxiv_id, normalize_arxiv_id
from db import get_session
from models import (
    Paper,
    PaperCreate,
    PaperRead,
    PaperUpdate,
    Status,
    TagCount,
    normalize_tags,
)

app = FastAPI(title="paper-shelf API")

# ブラウザ（localhost:3000 の frontend）から直接 fetch できるようにする
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # 受け付けない項目が送られてきたときは、どの項目が駄目なのかを日本語で返す
    extra = [str(e["loc"][-1]) for e in exc.errors() if e["type"] == "extra_forbidden"]
    if extra:
        return JSONResponse(
            status_code=422,
            content={"detail": f"受け付けていない項目です: {', '.join(extra)}"},
        )
    return await request_validation_exception_handler(request, exc)


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
    status: Status | None = None,
    author: str | None = None,
    q: str | None = None,
    sort: Literal["created_at", "published"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    session: Session = Depends(get_session),
):
    stmt = select(Paper)
    tags = normalize_tags(tag)
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


@app.patch("/papers/{paper_id}", response_model=PaperRead)
def update_paper(
    paper_id: int, body: PaperUpdate, session: Session = Depends(get_session)
):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "論文が見つかりません")
    # exclude_unset: 送られてこなかった項目は触らない（None で上書きしない）
    paper.sqlmodel_update(body.model_dump(exclude_unset=True, exclude_none=True))
    session.add(paper)
    session.commit()
    session.refresh(paper)
    return paper


@app.delete("/papers/{paper_id}", status_code=204)
def delete_paper(paper_id: int, session: Session = Depends(get_session)):
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "論文が見つかりません")
    session.delete(paper)
    session.commit()
    return Response(status_code=204)


@app.get("/tags", response_model=list[TagCount])
def list_tags(session: Session = Depends(get_session)):
    # SELECT unnest(tags) AS name, count(*) FROM papers GROUP BY name
    name = func.unnest(Paper.tags).label("name")
    sub = select(name).subquery()
    stmt = (
        select(sub.c.name, func.count().label("count"))
        .group_by(sub.c.name)
        .order_by(func.count().desc(), sub.c.name)
    )
    return [TagCount(name=n, count=c) for n, c in session.exec(stmt).all()]

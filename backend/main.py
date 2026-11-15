import re
from collections import Counter
from itertools import combinations
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import exists, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, or_, select

from arxiv import (
    ArxivUnavailable,
    PaperNotFound,
    fetch_paper,
    is_valid_arxiv_id,
    normalize_arxiv_id,
)
from db import get_session
from models import (
    Graph,
    GraphEdge,
    GraphNode,
    Paper,
    PaperCreate,
    PaperRead,
    PaperUpdate,
    Status,
    TagCount,
    YearCount,
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
    # FastAPI 標準の英語のエラーを、どの項目がなぜ駄目なのかが分かる日本語 1 文にする
    errors = exc.errors()
    # 受け付けない項目は 1 文にまとめる（「受け付けていない項目です: title, authors」）
    extra = [str(e["loc"][-1]) for e in errors if e["type"] == "extra_forbidden"]
    messages = [f"受け付けていない項目です: {', '.join(extra)}"] if extra else []
    messages += [validation_message(e) for e in errors if e["type"] != "extra_forbidden"]
    return JSONResponse(
        status_code=422,
        content={
            "detail": " / ".join(dict.fromkeys(messages)),  # 同じ文は 1 回だけ
            "errors": [{"loc": list(e["loc"]), "type": e["type"]} for e in errors],
        },
    )


def validation_message(e: dict) -> str:
    # loc は ("body", "tags", 0) のようにリストの番号で終わることがあるので、最後の名前を使う
    field = next((x for x in reversed(e["loc"]) if isinstance(x, str)), "")
    ctx = e.get("ctx") or {}
    match e["type"]:
        case "missing":
            return f"「{field}」がありません"
        case "literal_error":
            # pydantic の "'unread', 'reading' or 'read'" を "unread / reading / read" にする
            choices = re.sub(r"'|\bor\b", "", str(ctx.get("expected", ""))).replace(",", " ")
            return f"「{field}」は {' / '.join(choices.split())} のどれかにしてください"
        case "int_parsing" | "int_type":
            return f"「{field}」は整数にしてください"
        case "greater_than_equal":
            return f"「{field}」は {ctx.get('ge')} 以上にしてください"
        case "string_type":
            return f"「{field}」は文字列にしてください"
        case "list_type":
            return f"「{field}」は配列にしてください"
        case "value_error":
            # 自前のチェック（models.py の _reject_null など）の文をそのまま使う
            return str(e["msg"]).removeprefix("Value error, ")
        case "json_invalid":
            return "送られてきた内容を JSON として読めません"
        case _:
            return f"「{field}」の値が正しくありません"


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
    except PaperNotFound as e:
        raise HTTPException(404, str(e))
    except ArxivUnavailable as e:
        raise HTTPException(502, str(e))

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
    # 同じ日付の論文の並びが毎回変わらないよう、id でも並べる
    stmt = stmt.order_by(
        sort_col.desc() if order == "desc" else sort_col.asc(), col(Paper.id).desc()
    )
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


@app.get("/stats/years", response_model=list[YearCount])
def stats_years(session: Session = Depends(get_session)):
    # SELECT extract(year FROM published) AS year, count(*) FROM papers GROUP BY year
    year = func.extract("year", Paper.published).label("year")
    stmt = select(year, func.count().label("count")).group_by(year).order_by(year)
    return [YearCount(year=int(y), count=c) for y, c in session.exec(stmt).all()]


def cooccurrence_graph(groups: list[list[str]], min_count: int = 1) -> Graph:
    """
    groups は「一緒に出てきた名前の組」の一覧（論文ごとのタグや著者）。
    min_count 本以上に出てくる名前をノードにし、同じ論文に出てきた 2 つを線で結ぶ
    """
    counts = Counter(name for g in groups for name in set(g))
    keep = {name for name, c in counts.items() if c >= min_count}
    weights: Counter[tuple[str, str]] = Counter()
    for g in groups:
        for a, b in combinations(sorted(set(g) & keep), 2):
            weights[(a, b)] += 1
    return Graph(
        nodes=[GraphNode(id=n, count=counts[n]) for n in sorted(keep, key=lambda n: (-counts[n], n))],
        edges=[GraphEdge(source=a, target=b, weight=w) for (a, b), w in weights.items()],
    )


@app.get("/graph/tags", response_model=Graph)
def graph_tags(session: Session = Depends(get_session)):
    return cooccurrence_graph(list(session.exec(select(Paper.tags)).all()))


@app.get("/graph/authors", response_model=Graph)
def graph_authors(
    max_authors: int = Query(default=20, ge=1),
    min_papers: int = Query(default=2, ge=1),
    session: Session = Depends(get_session),
):
    # 著者が何百人もいる論文が 1 本あるだけでグラフが埋まるので、max_authors 人を超える論文は除く
    groups = [a for a in session.exec(select(Paper.authors)).all() if len(a) <= max_authors]
    return cooccurrence_graph(groups, min_papers)

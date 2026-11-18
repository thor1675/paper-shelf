import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy import exists, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, or_, select

from arxiv import (
    SEARCH_BUSY_MESSAGE,
    SEARCH_UNAVAILABLE_MESSAGE,
    ArxivBusy,
    ArxivUnavailable,
    PaperNotFound,
    fetch_paper,
    fetch_papers,
    search_arxiv,
    is_valid_arxiv_id,
    normalize_arxiv_id,
)
from auth import current_user
from auth import router as auth_router
from bibtex import to_bibtex
from citations import router as citations_router
from citations import sync_new_papers
from db import get_session
import translation
from models import (
    BatchCreate,
    BatchItem,
    BulkResult,
    BulkUpdate,
    MonthCount,
    ReadStats,
    TagChange,
    TagRename,
    Translation,
    TranslationStatus,
    Graph,
    GraphEdge,
    GraphNode,
    Paper,
    PaperCreate,
    PaperRead,
    PaperUpdate,
    SearchItem,
    SearchResult,
    ShelfEntry,
    Status,
    TagCount,
    User,
    Watch,
    WatchCreate,
    WatchRead,
    WatchSeen,
    YearCount,
    normalize_tags,
)

# arxiv.py などの警告を docker compose logs backend で読めるようにする
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="PAPER - Shelf API")
app.include_router(auth_router)
app.include_router(citations_router)

# ブラウザ（localhost:3000 の frontend）から直接 fetch できるようにする。
# ログインの Cookie を送ってもらうため allow_credentials を付ける（このとき送り元は * にできない）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
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


def shelve(session: Session, user: User, paper: Paper) -> ShelfEntry | None:
    """論文をその人の本棚に入れる。すでに入っていれば None"""
    entry = ShelfEntry(user_id=user.id, paper_id=paper.id)
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:
        # 同じ人が同じ論文を同時に登録した場合
        session.rollback()
        return None
    session.refresh(entry)
    return entry


def get_or_create_paper(session: Session, data: dict) -> Paper:
    """arXiv から取った論文を共有の papers に入れる。ほかの人が同時に入れていたらそれを使う"""
    paper = Paper(**data)
    session.add(paper)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return session.exec(select(Paper).where(Paper.arxiv_id == data["arxiv_id"])).one()
    session.refresh(paper)
    return paper


@app.post("/papers", response_model=PaperRead, status_code=201)
def create_paper(
    body: PaperCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    arxiv_id = normalize_arxiv_id(body.arxiv_id)
    if not is_valid_arxiv_id(arxiv_id):
        raise HTTPException(400, f"arXiv ID の形式ではありません: {body.arxiv_id}")

    # ほかの人が登録済みの論文なら、arXiv に問い合わせずに本棚に入れる
    paper = session.exec(select(Paper).where(Paper.arxiv_id == arxiv_id)).first()
    if paper and session.exec(
        select(ShelfEntry.id).where(ShelfEntry.user_id == user.id, ShelfEntry.paper_id == paper.id)
    ).first():
        raise HTTPException(409, f"{arxiv_id} は登録済みです")

    if not paper:
        try:
            data = fetch_paper(arxiv_id)
        except PaperNotFound as e:
            raise HTTPException(404, str(e))
        except ArxivBusy as e:
            raise HTTPException(503, str(e))
        except ArxivUnavailable as e:
            raise HTTPException(502, str(e))
        paper = get_or_create_paper(session, data)
        # 被引用数と参考文献は、応答を返したあとに裏で OpenAlex から取る
        background_tasks.add_task(sync_new_papers, [paper.id])

    entry = shelve(session, user, paper)
    if not entry:
        raise HTTPException(409, f"{arxiv_id} は登録済みです")
    return PaperRead.of(paper, entry)


def paper_query(
    tag: list[str] = Query(default=[]),
    status: Status | None = None,
    author: str | None = None,
    q: str | None = None,
    sort: Literal["created_at", "published", "citations"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    user: User = Depends(current_user),
):
    """
    一覧の絞り込み条件から SELECT 文を組み立てる。一覧と BibTeX の書き出しで同じ条件を使う。
    ログイン中の人の本棚にある論文だけ。(Paper, ShelfEntry) の組を返す
    """
    stmt = select(Paper, ShelfEntry).join(ShelfEntry, col(ShelfEntry.paper_id) == col(Paper.id)).where(
        ShelfEntry.user_id == user.id
    )
    tags = normalize_tags(tag)
    if tags:
        # tags @> ARRAY[...]。指定したタグをすべて持つ論文（GIN インデックスが効く）
        stmt = stmt.where(col(ShelfEntry.tags).contains(tags))
    if status:
        stmt = stmt.where(ShelfEntry.status == status)
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
    sort_col = col(
        {"created_at": ShelfEntry.created_at, "published": Paper.published, "citations": Paper.citation_count}[sort]
    )
    # 被引用数がまだ分からない論文は、どちらの向きでも最後にする。
    # 同じ値の論文の並びが毎回変わらないよう、id でも並べる
    return stmt.order_by(
        (sort_col.desc() if order == "desc" else sort_col.asc()).nulls_last(), col(Paper.id).desc()
    )


@app.get("/papers", response_model=list[PaperRead])
def list_papers(stmt=Depends(paper_query), session: Session = Depends(get_session)):
    return [PaperRead.of(p, e) for p, e in session.exec(stmt).all()]


# /papers/{paper_id} より前に置く（後ろだと export.bib が論文の番号として解釈されて 422 になる）
@app.get("/papers/export.bib", response_class=PlainTextResponse)
def export_bibtex(stmt=Depends(paper_query), session: Session = Depends(get_session)):
    return PlainTextResponse(
        to_bibtex([p for p, _ in session.exec(stmt).all()]),
        media_type="application/x-bibtex; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="paper-shelf.bib"'},
    )


@app.post("/papers/batch", response_model=list[BatchItem])
def create_papers_batch(
    body: BatchCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """
    まとめて登録する。arXiv には 1 回の問い合わせでまとめて取りに行く
    （1 件ずつだと、3 秒に 1 回の制限で 20 件に 1 分かかる）
    """
    results: list[BatchItem] = []
    pending: list[BatchItem] = []
    seen: set[str] = set()
    for raw in body.items:
        arxiv_id = normalize_arxiv_id(raw)
        if not is_valid_arxiv_id(arxiv_id):
            results.append(BatchItem(input=raw, arxiv_id=None, result="invalid"))
            continue
        if arxiv_id in seen:
            results.append(BatchItem(input=raw, arxiv_id=arxiv_id, result="duplicate"))
            continue
        seen.add(arxiv_id)
        item = BatchItem(input=raw, arxiv_id=arxiv_id, result="not_found")
        results.append(item)
        pending.append(item)

    # 自分の本棚にあるものは「登録済み」。ほかの人が登録済みの論文は arXiv に聞かずに本棚に入れる
    known = {
        p.arxiv_id: p
        for p in session.exec(select(Paper).where(col(Paper.arxiv_id).in_([i.arxiv_id for i in pending])))
    }
    mine = set(
        session.exec(
            select(ShelfEntry.paper_id).where(
                ShelfEntry.user_id == user.id, col(ShelfEntry.paper_id).in_([p.id for p in known.values()])
            )
        ).all()
    )

    def put(item: BatchItem, paper: Paper) -> None:
        if paper.id in mine or not shelve(session, user, paper):
            item.result = "exists"
        else:
            item.result = "created"
        item.paper_id, item.title = paper.id, paper.title

    for item in pending:
        if item.arxiv_id in known:
            put(item, known[item.arxiv_id])
    pending = [i for i in pending if i.result == "not_found"]

    try:
        found = fetch_papers([i.arxiv_id for i in pending])
    except ArxivUnavailable as e:
        for item in pending:
            item.result = "busy" if isinstance(e, ArxivBusy) else "unavailable"
        return results

    new_papers: list[int] = []
    for item in pending:
        if item.arxiv_id in found:
            paper = get_or_create_paper(session, found[item.arxiv_id])
            new_papers.append(paper.id)
            put(item, paper)
    if new_papers:
        background_tasks.add_task(sync_new_papers, new_papers)
    return results


def shelf_entry(session: Session, user: User, paper_id: int) -> tuple[Paper, ShelfEntry]:
    """その人の本棚にある論文。ほかの人の本棚にしかない論文も「見つかりません」にする"""
    row = session.exec(
        select(Paper, ShelfEntry)
        .join(ShelfEntry, col(ShelfEntry.paper_id) == col(Paper.id))
        .where(Paper.id == paper_id, ShelfEntry.user_id == user.id)
    ).first()
    if not row:
        raise HTTPException(404, "論文が見つかりません")
    return row


def user_entries(user: User):
    """その人の本棚の行を選ぶ SELECT 文"""
    return select(ShelfEntry).where(ShelfEntry.user_id == user.id)


@app.get("/papers/{paper_id}", response_model=PaperRead)
def get_paper(paper_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return PaperRead.of(*shelf_entry(session, user, paper_id))


def set_status(entry: ShelfEntry, status: str) -> None:
    """ステータスを変える。「読了」にした日時を記録し、読了以外に戻したら消す"""
    if status == "read" and entry.status != "read":
        entry.read_at = datetime.now(timezone.utc)
    elif status != "read":
        entry.read_at = None
    entry.status = status


@app.post("/papers/bulk", response_model=BulkResult)
def bulk_update(body: BulkUpdate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """選んだ論文に、まとめてタグを付け外しする・ステータスを変える・本棚から外す"""
    papers = session.exec(user_entries(user).where(col(ShelfEntry.paper_id).in_(body.ids))).all()
    if body.delete:
        for p in papers:
            session.delete(p)
        session.commit()
        return BulkResult(updated=0, deleted=len(papers))
    for p in papers:
        # 配列の列は、新しい list を入れ直さないと変更が保存されない
        p.tags = normalize_tags([t for t in p.tags if t not in body.remove_tags] + body.add_tags)
        if body.status:
            set_status(p, body.status)
        session.add(p)
    session.commit()
    return BulkResult(updated=len(papers), deleted=0)


@app.patch("/papers/{paper_id}", response_model=PaperRead)
def update_paper(
    paper_id: int, body: PaperUpdate, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    paper, entry = shelf_entry(session, user, paper_id)
    # exclude_unset: 送られてこなかった項目は触らない（None で上書きしない）
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "status" in changes:
        set_status(entry, changes.pop("status"))
    entry.sqlmodel_update(changes)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    session.refresh(paper)
    return PaperRead.of(paper, entry)


@app.delete("/papers/{paper_id}", status_code=204)
def delete_paper(paper_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """本棚から外す（論文の情報と訳文は、ほかの人も使うので残す）"""
    _, entry = shelf_entry(session, user, paper_id)
    session.delete(entry)
    session.commit()
    return Response(status_code=204)


@app.post("/tags/rename", response_model=TagChange)
def rename_tag(body: TagRename, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """タグの名前を変える。既にあるタグの名前にすると 1 つにまとまる（同じ論文に 2 回は付かない）"""
    old, new = normalize_tags([body.old]), normalize_tags([body.new])
    if not old or not new:
        raise HTTPException(422, "タグの名前が空です")
    papers = session.exec(user_entries(user).where(col(ShelfEntry.tags).contains(old))).all()
    if not papers:
        raise HTTPException(404, f"「{old[0]}」というタグはありません")
    for p in papers:
        p.tags = normalize_tags([new[0] if t == old[0] else t for t in p.tags])
        session.add(p)
    session.commit()
    return TagChange(papers=len(papers))


@app.delete("/tags/{name}", response_model=TagChange)
def delete_tag(name: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """タグを全部の論文から外す（論文は消さない）"""
    tag = normalize_tags([name])
    papers = session.exec(user_entries(user).where(col(ShelfEntry.tags).contains(tag))).all() if tag else []
    if not papers:
        raise HTTPException(404, f"「{name}」というタグはありません")
    for p in papers:
        p.tags = [t for t in p.tags if t != tag[0]]
        session.add(p)
    session.commit()
    return TagChange(papers=len(papers))


@app.get("/stats/read", response_model=ReadStats)
def stats_read(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """月ごとに何本「読了」にしたか（日本時間の月で数える）"""
    read = session.exec(user_entries(user).where(ShelfEntry.status == "read")).all()
    jst = timezone(timedelta(hours=9))
    months = Counter(p.read_at.astimezone(jst).strftime("%Y-%m") for p in read if p.read_at)
    return ReadStats(
        months=[MonthCount(month=m, count=c) for m, c in sorted(months.items())],
        unknown=sum(1 for p in read if p.read_at is None),
    )


@app.get("/tags", response_model=list[TagCount])
def list_tags(user: User = Depends(current_user), session: Session = Depends(get_session)):
    # SELECT unnest(tags) AS name, count(*) FROM shelf WHERE user_id = ? GROUP BY name
    name = func.unnest(ShelfEntry.tags).label("name")
    sub = select(name).where(ShelfEntry.user_id == user.id).subquery()
    stmt = (
        select(sub.c.name, func.count().label("count"))
        .group_by(sub.c.name)
        .order_by(func.count().desc(), sub.c.name)
    )
    return [TagCount(name=n, count=c) for n, c in session.exec(stmt).all()]


@app.get("/stats/years", response_model=list[YearCount])
def stats_years(user: User = Depends(current_user), session: Session = Depends(get_session)):
    # SELECT extract(year FROM published) AS year, count(*) FROM papers JOIN shelf ... GROUP BY year
    year = func.extract("year", Paper.published).label("year")
    stmt = (
        select(year, func.count().label("count"))
        .join(ShelfEntry, col(ShelfEntry.paper_id) == col(Paper.id))
        .where(ShelfEntry.user_id == user.id)
        .group_by(year)
        .order_by(year)
    )
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
def graph_tags(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return cooccurrence_graph(list(session.exec(select(ShelfEntry.tags).where(ShelfEntry.user_id == user.id)).all()))


@app.get("/graph/authors", response_model=Graph)
def graph_authors(
    max_authors: int = Query(default=20, ge=1),
    min_papers: int = Query(default=2, ge=1),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    # 著者が何百人もいる論文が 1 本あるだけでグラフが埋まるので、max_authors 人を超える論文は除く
    rows = session.exec(
        select(Paper.authors).join(ShelfEntry, col(ShelfEntry.paper_id) == col(Paper.id)).where(ShelfEntry.user_id == user.id)
    ).all()
    groups = [a for a in rows if len(a) <= max_authors]
    return cooccurrence_graph(groups, min_papers)


# --- arXiv 検索 ---


def with_registered(papers: list[dict], session: Session, user: User) -> list[SearchItem]:
    """arXiv の結果に、その人の本棚にあればその論文の id を付ける"""
    ids = [p["arxiv_id"] for p in papers]
    registered = dict(
        session.exec(
            select(Paper.arxiv_id, Paper.id)
            .join(ShelfEntry, col(ShelfEntry.paper_id) == col(Paper.id))
            .where(col(Paper.arxiv_id).in_(ids), ShelfEntry.user_id == user.id)
        ).all()
    )
    return [SearchItem(**p, paper_id=registered.get(p["arxiv_id"])) for p in papers]


@app.get("/arxiv/search", response_model=SearchResult)
def arxiv_search(
    q: str = Query(min_length=1, max_length=200),
    start: int = Query(default=0, ge=0, le=1000),
    sort: Literal["relevance", "newest"] = "relevance",
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    try:
        total, papers = search_arxiv(q, start=start, max_results=20, newest=sort == "newest")
    except ArxivBusy:
        raise HTTPException(503, SEARCH_BUSY_MESSAGE)
    except ArxivUnavailable:
        raise HTTPException(502, SEARCH_UNAVAILABLE_MESSAGE)
    return SearchResult(total=total, start=start, items=with_registered(papers, session, user))


# --- 新着の通知（キーワードの登録と、新着の取得） ---

# 覚えておく「知らせた論文の ID」の上限。古いものから捨てる
SEEN_LIMIT = 500


def own_watch(session: Session, user: User, watch_id: int) -> Watch:
    watch = session.get(Watch, watch_id)
    if not watch or watch.user_id != user.id:
        raise HTTPException(404, "キーワードが見つかりません")
    return watch


@app.get("/watches", response_model=list[WatchRead])
def list_watches(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return session.exec(select(Watch).where(Watch.user_id == user.id).order_by(col(Watch.id))).all()


@app.post("/watches", response_model=WatchRead, status_code=201)
def create_watch(body: WatchCreate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    query = " ".join(body.query.split())
    if session.exec(select(Watch).where(Watch.user_id == user.id, Watch.query == query)).first():
        raise HTTPException(409, f"「{query}」は登録済みです")
    watch = Watch(query=query, user_id=user.id)
    session.add(watch)
    session.commit()
    session.refresh(watch)
    return watch


@app.delete("/watches/{watch_id}", status_code=204)
def delete_watch(watch_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    watch = own_watch(session, user, watch_id)
    session.delete(watch)
    session.commit()
    return Response(status_code=204)


@app.get("/watches/{watch_id}/new", response_model=list[SearchItem])
def watch_new_papers(watch_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """
    キーワードの新着。投稿の新しい順に 30 件を見て、まだ知らせていない・登録していないものを返す。
    日付ではなく「知らせた ID」で判定するので、公開日と通知の時刻がずれても重複も取りこぼしも無い
    """
    watch = own_watch(session, user, watch_id)
    try:
        _, papers = search_arxiv(watch.query, max_results=30, newest=True)
    except ArxivBusy:
        raise HTTPException(503, SEARCH_BUSY_MESSAGE)
    except ArxivUnavailable:
        raise HTTPException(502, SEARCH_UNAVAILABLE_MESSAGE)
    items = with_registered([p for p in papers if p["arxiv_id"] not in watch.seen], session, user)
    return [i for i in items if i.paper_id is None]


@app.post("/watches/{watch_id}/seen", response_model=WatchRead)
def mark_watch_seen(
    watch_id: int, body: WatchSeen, user: User = Depends(current_user), session: Session = Depends(get_session)
):
    """知らせた論文の ID を記録する（Slack に流したあとに slackbot が呼ぶ）"""
    watch = own_watch(session, user, watch_id)
    merged = watch.seen + [i for i in body.arxiv_ids if i not in watch.seen]
    watch.seen = merged[-SEEN_LIMIT:]
    watch.notified_at = datetime.now(timezone.utc)
    session.add(watch)
    session.commit()
    session.refresh(watch)
    return watch


# --- 日本語で読む（翻訳） ---


def _paper_or_404(session: Session, user: User, paper_id: int) -> Paper:
    """訳文は全員で共有するが、見られるのは自分の本棚にある論文だけ"""
    return shelf_entry(session, user, paper_id)[0]


def _status(t: Translation | None) -> TranslationStatus:
    if t is None:
        return TranslationStatus(status=None)
    if translation.is_stale(t):
        return TranslationStatus(status="failed", done=t.done, total=t.total, error="翻訳が途中で止まりました。もう一度試してください")
    return TranslationStatus(status=t.status, done=t.done, total=t.total, source_url=t.source_url, error=t.error)


def run_translation(arxiv_id: str) -> None:
    """裏で 1 本を訳す（数分かかることがあるので、応答を返したあとに動かす）"""
    from db import engine

    with Session(engine) as session:
        translation.run(session, arxiv_id)


@app.get("/papers/{paper_id}/translation", response_model=TranslationStatus)
def translation_status(paper_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    paper = _paper_or_404(session, user, paper_id)
    return _status(session.get(Translation, paper.arxiv_id))


@app.post("/papers/{paper_id}/translation", response_model=TranslationStatus, status_code=202)
def start_translation(
    paper_id: int,
    background_tasks: BackgroundTasks,
    force: bool = False,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """翻訳を始める。訳し終えていれば（force でなければ）そのまま返す。訳している最中なら二重に始めない"""
    paper = _paper_or_404(session, user, paper_id)
    t = session.get(Translation, paper.arxiv_id)
    if t and not translation.is_stale(t) and (t.status in ("queued", "running") or (t.status == "done" and not force)):
        return _status(t)
    t = t or Translation(arxiv_id=paper.arxiv_id)
    t.status, t.done, t.total, t.error, t.html = "queued", 0, 0, None, None
    t.updated_at = datetime.now(timezone.utc)
    session.add(t)
    session.commit()
    session.refresh(t)
    background_tasks.add_task(run_translation, paper.arxiv_id)
    return _status(t)


# 訳した HTML はスクリプトを一切動かさない（arXiv から取ってきたものなので）。画像と CSS は arXiv から読む
TRANSLATION_CSP = (
    "default-src 'none'; img-src https: data:; style-src 'unsafe-inline' https:; font-src https: data:; "
    "frame-ancestors http://localhost:3000"
)


@app.get("/papers/{paper_id}/translation.html", response_class=HTMLResponse)
def translation_html(paper_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    paper = _paper_or_404(session, user, paper_id)
    t = session.get(Translation, paper.arxiv_id)
    if not t or t.status != "done" or not t.html:
        raise HTTPException(404, "まだ訳していません")
    return HTMLResponse(t.html, headers={"Content-Security-Policy": TRANSLATION_CSP})

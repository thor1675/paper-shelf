"""引用・被引用の関係（OpenAlex）"""

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

import scholar
from arxiv import is_valid_arxiv_id, normalize_arxiv_id
from auth import current_user
from db import get_session
from models import (
    CitationMap,
    CitationNode,
    LibraryEdge,
    LibraryGraph,
    LibraryNode,
    MissingItem,
    Paper,
    ScholarCache,
    ShelfEntry,
    SyncResult,
    User,
)

router = APIRouter(prefix="/citations", tags=["citations"])

# OpenAlex から取った結果をとっておく期間
CACHE_DAYS = 7


# --- とっておいた結果の出し入れ ---


def cache_get(session: Session, key: str):
    row = session.get(ScholarCache, key)
    if row and row.fetched_at > datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS):
        return row.data
    return None


def cache_put(session: Session, key: str, data) -> None:
    row = session.get(ScholarCache, key) or ScholarCache(key=key, data=data)
    row.data, row.fetched_at = data, datetime.now(timezone.utc)
    session.add(row)
    session.commit()


def node_lookup(session: Session, work_ids: list[str]) -> dict[str, dict]:
    """OpenAlex の ID から 1 本分の情報を引く。とっておいたものは使い、無いものだけまとめて問い合わせる"""
    result: dict[str, dict] = {}
    missing = []
    for wid in work_ids:
        cached = cache_get(session, f"node:{wid}")
        if cached is None:
            missing.append(wid)
        else:
            result[wid] = cached
    if missing:
        for wid, w in scholar.works_by_ids(missing).items():
            node = scholar.to_node(w)
            cache_put(session, f"node:{wid}", node)
            result[wid] = node
    return result


def my_papers(session: Session, user: User) -> list[Paper]:
    """その人の本棚にある論文"""
    return list(
        session.exec(
            select(Paper).join(ShelfEntry, col(ShelfEntry.paper_id) == col(Paper.id)).where(ShelfEntry.user_id == user.id)
        ).all()
    )


def with_paper_ids(session: Session, nodes: list[dict], user: User) -> list[CitationNode]:
    """その人の本棚にある論文なら paper_id を付ける（arXiv の番号か OpenAlex の ID で照らし合わせる）"""
    arxiv_ids = [n["arxiv_id"] for n in nodes if n.get("arxiv_id")]
    work_ids = [n["work_id"] for n in nodes]
    mine = select(Paper).join(ShelfEntry, col(ShelfEntry.paper_id) == col(Paper.id)).where(ShelfEntry.user_id == user.id)
    by_arxiv = {p.arxiv_id: p.id for p in session.exec(mine.where(col(Paper.arxiv_id).in_(arxiv_ids))).all()}
    by_work = {p.openalex_id: p.id for p in session.exec(mine.where(col(Paper.openalex_id).in_(work_ids))).all()}
    return [
        CitationNode(**{**n, "paper_id": by_arxiv.get(n.get("arxiv_id")) or by_work.get(n["work_id"])})
        for n in nodes
    ]


def parse_key(key: str) -> str:
    """図の中心にする論文。arXiv の ID・URL か、OpenAlex の ID（W…）"""
    key = key.strip()
    if re.fullmatch(r"[Ww]\d+", key):
        return key.upper()
    arxiv_id = normalize_arxiv_id(key)
    if not is_valid_arxiv_id(arxiv_id):
        raise HTTPException(400, f"arXiv ID か OpenAlex の ID（W から始まる）を指定してください: {key}")
    return arxiv_id


def fetch_work(key: str) -> dict:
    try:
        return scholar.work(key)
    except scholar.WorkNotFound:
        raise HTTPException(404, f"{key} の引用の情報は見つかりませんでした")
    except scholar.ScholarUnavailable as e:
        raise HTTPException(502, str(e))


# --- 1 本を中心にした引用の図 ---


@router.get("/map", response_model=CitationMap)
def citation_map(
    key: str = Query(min_length=1, max_length=100),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """
    この論文の参考文献（引用している論文）と、この論文を引用している論文。
    引用している論文は被引用数の多い 30 本だけを返す（何万本もあることがあるため）
    """
    key = parse_key(key)
    data = cache_get(session, f"map:{key}")
    if data is None:
        w = fetch_work(key)
        try:
            refs = node_lookup(session, [scholar.short_id(r) for r in w.get("referenced_works") or []])
            total, citing = scholar.citing_works(scholar.short_id(w["id"]), 30)
        except scholar.ScholarUnavailable as e:
            raise HTTPException(502, str(e))
        data = {
            "center": scholar.to_node(w),
            "references": sorted(refs.values(), key=lambda n: -(n["cited_by_count"] or 0)),
            "references_total": len(w.get("referenced_works") or []),
            "citations": [scholar.to_node(c) for c in citing],
            "citations_total": total,
        }
        cache_put(session, f"map:{key}", data)
    return CitationMap(
        center=with_paper_ids(session, [data["center"]], user)[0],
        references=with_paper_ids(session, data["references"], user),
        citations=with_paper_ids(session, data["citations"], user),
        references_total=data["references_total"],
        citations_total=data["citations_total"],
    )


@router.get("/related", response_model=list[CitationNode])
def related(
    key: str = Query(min_length=1, max_length=100),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """おすすめの論文（OpenAlex が分野や内容の近さで選んだもの）"""
    key = parse_key(key)
    data = cache_get(session, f"related:{key}")
    if data is None:
        w = fetch_work(key)
        try:
            nodes = node_lookup(session, [scholar.short_id(r) for r in w.get("related_works") or []])
        except scholar.ScholarUnavailable as e:
            raise HTTPException(502, str(e))
        data = sorted(nodes.values(), key=lambda n: -(n["cited_by_count"] or 0))
        cache_put(session, f"related:{key}", data)
    return with_paper_ids(session, data, user)


# --- 登録した論文の同期 ---


def sync_papers(session: Session, papers: list[Paper]) -> SyncResult:
    """OpenAlex から被引用数と参考文献を取ってきて、論文に書き込む"""
    if not papers:
        return SyncResult(synced=0, not_found=0)
    works = scholar.works_by_arxiv(
        [p.arxiv_id for p in papers], fields="id,doi,cited_by_count,referenced_works,locations"
    )
    now = datetime.now(timezone.utc)
    synced = 0
    for p in papers:
        w = works.get(p.arxiv_id)
        if w:
            p.openalex_id = scholar.short_id(w["id"])
            p.citation_count = w.get("cited_by_count") or 0
            p.reference_ids = [scholar.short_id(r) for r in w.get("referenced_works") or []]
            synced += 1
        # 見つからなかった論文も日時を記録し、毎回問い合わせないようにする（7 日後にもう一度見る）
        p.scholar_synced_at = now
        session.add(p)
    session.commit()
    return SyncResult(synced=synced, not_found=len(papers) - synced)


@router.post("/sync", response_model=SyncResult)
def sync(force: bool = False, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """
    本棚の論文のうち、まだ同期していないものと、同期から 7 日たったものを更新する（force なら全部）。
    被引用数などは共有の情報なので、ほかの人の本棚にも反映される
    """
    stmt = select(Paper).join(ShelfEntry, col(ShelfEntry.paper_id) == col(Paper.id)).where(ShelfEntry.user_id == user.id)
    if not force:
        stale = datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)
        stmt = stmt.where(
            (col(Paper.scholar_synced_at).is_(None)) | (col(Paper.scholar_synced_at) < stale)
        )
    try:
        return sync_papers(session, list(session.exec(stmt).all()))
    except scholar.ScholarUnavailable as e:
        raise HTTPException(502, str(e))


def sync_new_papers(paper_ids: list[int]) -> None:
    """登録した直後に裏で同期する（登録の応答は待たせない）。失敗しても次の同期で拾う"""
    from db import engine

    with Session(engine) as session:
        papers = [p for p in (session.get(Paper, i) for i in paper_ids) if p]
        try:
            sync_papers(session, papers)
        except scholar.ScholarUnavailable:
            pass


# --- 登録した論文どうしの引用ネットワーク ---


def short_label(p: Paper) -> str:
    """図の円に付ける短い名前（Vaswani 2017）"""
    last = p.authors[0].split()[-1] if p.authors else "?"
    return f"{last} {p.published.year}"


@router.get("/library", response_model=LibraryGraph)
def library(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """本棚の論文のうち、誰が誰を引用しているか。DB だけで計算する（OpenAlex には問い合わせない）"""
    papers = my_papers(session, user)
    by_work = {p.openalex_id: p for p in papers if p.openalex_id}
    edges = [
        LibraryEdge(source=p.id, target=by_work[r].id)
        for p in papers
        for r in p.reference_ids
        if r in by_work and by_work[r].id != p.id
    ]
    linked = [p for p in papers if p.id in {e.source for e in edges} | {e.target for e in edges}]
    # 同じ名前（Weller 2024 が 3 本など）は、公開日の順に a, b, c を付けて区別する
    labels = {p.id: short_label(p) for p in linked}
    dup = Counter(labels.values())
    seen: Counter[str] = Counter()
    for p in sorted(linked, key=lambda p: (p.published, p.id)):
        if dup[labels[p.id]] > 1:
            base = labels[p.id]
            labels[p.id] = base + "abcdefghijklmnopqrstuvwxyz"[seen[base]]
            seen[base] += 1
    nodes = [
        LibraryNode(
            paper_id=p.id,
            title=p.title,
            label=labels[p.id],
            year=p.published.year,
            cited_by_count=p.citation_count,
        )
        for p in linked
    ]
    return LibraryGraph(
        nodes=nodes, edges=edges, unsynced=sum(1 for p in papers if p.scholar_synced_at is None)
    )


@router.get("/missing", response_model=list[MissingItem])
def missing(
    min_count: int = Query(default=2, ge=1, le=20),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """本棚の論文がよく参考文献に挙げているのに、まだ本棚にない論文"""
    papers = my_papers(session, user)
    registered = {p.openalex_id for p in papers if p.openalex_id}
    cited_by: dict[str, list[int]] = {}
    for p in papers:
        for r in set(p.reference_ids) - registered:
            cited_by.setdefault(r, []).append(p.id)
    counts = Counter({r: len(ps) for r, ps in cited_by.items() if len(ps) >= min_count})
    top = [r for r, _ in counts.most_common(limit)]
    try:
        nodes = node_lookup(session, top)
    except scholar.ScholarUnavailable as e:
        raise HTTPException(502, str(e))
    items = with_paper_ids(session, [nodes[r] for r in top if r in nodes], user)
    return [MissingItem(**i.model_dump(), cited_by_papers=sorted(cited_by[i.work_id])) for i in items]

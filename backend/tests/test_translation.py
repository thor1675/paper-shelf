"""日本語で読む（arXiv の HTML 版を、構造を保ったまま訳す）。translator と arXiv は偽物に差し替える"""

import re

import pytest

import main
import translation
from test_api import add

PAGE = """<!DOCTYPE html><html><head><title>T</title>
<link rel="stylesheet" href="/static/browse/css/arxiv.css"><script>alert(1)</script></head><body>
<article class="ltx_document">
<h1 class="ltx_title ltx_title_document">Attention <br class="ltx_break"/>Is All You Need</h1>
<div class="ltx_authors"><span class="ltx_personname">Ashish Vaswani</span></div>
<div class="ltx_abstract"><p class="ltx_p">We propose the Transformer. It is fast.</p></div>
<section class="ltx_section"><h2 class="ltx_title ltx_title_section">Introduction</h2>
<div class="ltx_para"><p id="S1.p1" class="ltx_p" onclick="steal()">The score is <math class="ltx_Math" alttext="x"><mi>x</mi></math>
as in <cite class="ltx_cite"><a href="#bib.bib1" class="ltx_ref">Smith (2020)</a></cite> and <span class="ltx_text ltx_font_italic">shown</span> in
<a href="#S1.F1" class="ltx_ref">Figure 1</a>.</p></div>
<figure id="S1.F1"><img src="1706.03762v7/fig1.png"><figcaption>Figure 1: The model architecture.</figcaption></figure>
<table class="ltx_tabular"><tr><td>BLEU 28.4</td></tr></table>
<p class="ltx_p"><a href="javascript:steal()">bad link</a> and <a href="https://example.com/x">good link</a> here.</p>
<p class="ltx_p">12.3</p>
</section>
<section class="ltx_bibliography"><ul><li><p class="ltx_p">Smith. Some paper. 2020.</p></li></ul></section>
</article></body></html>"""

URL = "https://arxiv.org/html/1706.03762"


def fake_translate(texts):
    """訳したことが分かるよう「訳:」を付ける。目印はそのまま書き写す（本物の FuguMT と同じ）"""
    return [f"訳:{t}" for t in texts]


# --- 部品 ---


def test_flatten_replaces_inline_elements_with_marks():
    soup, blocks = translation.prepare(PAGE, URL)
    p = soup.find(id="S1.p1")
    text, kept = translation.flatten(p)
    # 数式は XMATH、引用・参照は XREF。斜体は文だけ残す
    assert text == "The score is XMATH1 as in XREF2 and shown in XREF3 ."
    assert kept[0].startswith("<math") and kept[1].startswith("<cite") and kept[2].startswith('<a class="ltx_ref" href="#S1.F1"')


@pytest.mark.parametrize(
    "translated, expected",
    [
        ("スコアは XMATH1 で XREF2", "スコアは <m> で <c>"),
        ("スコアは XMATH 1 で XREF 2", "スコアは <m> で <c>"),   # 空白が入っても戻す
        ("スコアは XMATH1", "スコアは <m>（<c>）"),               # 消えた目印は最後に付け足す
        ("a < b & XMATH1 XREF2", "a &lt; b &amp; <m> <c>"),       # 訳文はエスケープする
        ("XMATH1 XMATH1 XREF2", "<m>  <c>"),                       # 同じ目印は 1 回だけ戻す
    ],
)
def test_restore(translated, expected):
    assert translation.restore(translated, ["<m>", "<c>"]) == expected


def test_prepare_sanitizes_and_selects_blocks():
    soup, blocks = translation.prepare(PAGE, URL)
    out = str(soup)
    assert "<script" not in out and "onclick" not in out and "javascript:" not in out
    # 画像と CSS は arXiv の絶対 URL に、ページ内のリンクはそのまま、外へのリンクは新しいタブ
    assert 'src="https://arxiv.org/html/1706.03762v7/fig1.png"' in out
    assert 'href="https://arxiv.org/static/browse/css/arxiv.css"' in out
    assert 'href="#S1.F1"' in out
    assert 'href="https://example.com/x" rel="noopener noreferrer" target="_blank"' in out
    texts = [b.get_text(" ", strip=True) for b in blocks]
    # 著者・表・参考文献・文字の無い段落は訳さない
    assert not any("Vaswani" in t or "BLEU" in t or "Some paper" in t or t == "12.3" for t in texts)
    assert any(t.startswith("Introduction") for t in texts) and any("architecture" in t for t in texts)


# --- 通しで訳す ---


@pytest.fixture
def fake_sources(monkeypatch):
    monkeypatch.setattr(translation, "fetch_html", lambda arxiv_id: (PAGE, URL))
    monkeypatch.setattr(translation, "translate_texts", fake_translate)


def test_translate_paper_end_to_end(client, fake_sources):
    p = add(client, "1706.03762")
    assert client.get(f"/papers/{p['id']}/translation").json()["status"] is None
    assert client.get(f"/papers/{p['id']}/translation.html").status_code == 404

    # 始めると裏で訳す（テストでは応答のあとすぐ終わる）
    assert client.post(f"/papers/{p['id']}/translation").status_code == 202
    st = client.get(f"/papers/{p['id']}/translation").json()
    assert st["status"] == "done" and st["done"] == st["total"] > 0 and st["source_url"] == URL

    res = client.get(f"/papers/{p['id']}/translation.html")
    assert res.status_code == 200
    assert "default-src 'none'" in res.headers["content-security-policy"]  # スクリプトを動かさない
    page = res.text
    assert "機械翻訳した訳文です" in page and "公開や共有はしないでください" in page
    # 数式・引用・参照は元の要素に戻り、目印は残らない。原文はたためる形で付く
    assert not re.search(r"X\s?(?:MATH|REF)\s?\d", page.split("ps-banner")[1])
    assert '訳:The score is <math alttext="x" class="ltx_Math"' in page
    assert '<details class="ps-orig"><summary>原文</summary>The score is' in page
    # 見出しは訳し、原文は title に（目印ではなく元の文）
    assert 'title="Attention Is All You Need"' in page and ">訳:Introduction<" in page
    # 参考文献は訳さない
    assert "Smith. Some paper. 2020." in page and "訳:Smith" not in page


def test_done_translation_is_not_redone_unless_forced(client, fake_sources, monkeypatch):
    p = add(client, "1706.03762")
    client.post(f"/papers/{p['id']}/translation")
    calls = []
    monkeypatch.setattr(translation, "translate_texts", lambda t: calls.append(1) or fake_translate(t))
    client.post(f"/papers/{p['id']}/translation")
    assert calls == []
    client.post(f"/papers/{p['id']}/translation?force=true")
    assert calls


def test_no_html_version(client, monkeypatch):
    def none(arxiv_id):
        raise translation.NoHtml(arxiv_id)

    monkeypatch.setattr(translation, "fetch_html", none)
    p = add(client, "1706.03762")
    client.post(f"/papers/{p['id']}/translation")
    st = client.get(f"/papers/{p['id']}/translation").json()
    assert st["status"] == "failed"
    assert st["error"] == "この論文には HTML 版がありません（arXiv にも ar5iv にもありませんでした）"


def test_translator_down(client, monkeypatch):
    import httpx

    def down(texts):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(translation, "fetch_html", lambda arxiv_id: (PAGE, URL))
    monkeypatch.setattr(translation, "translate_texts", down)
    p = add(client, "1706.03762")
    client.post(f"/papers/{p['id']}/translation")
    st = client.get(f"/papers/{p['id']}/translation").json()
    assert st["status"] == "failed" and "translator が起動しているか" in st["error"]


def test_stale_running_job_can_restart(client, fake_sources):
    from datetime import datetime, timedelta, timezone

    import psycopg

    import conftest

    p = add(client, "1706.03762")
    # backend が止まって、訳している途中のまま 1 時間たった
    with psycopg.connect(conftest.TEST_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO translations (arxiv_id, status, done, total, updated_at) VALUES (%s, 'running', 3, 10, %s)",
            ("1706.03762", datetime.now(timezone.utc) - timedelta(hours=1)),
        )
    st = client.get(f"/papers/{p['id']}/translation").json()
    assert st["status"] == "failed" and st["error"] == "翻訳が途中で止まりました。もう一度試してください"
    client.post(f"/papers/{p['id']}/translation")
    assert client.get(f"/papers/{p['id']}/translation").json()["status"] == "done"


def test_translation_404(client):
    assert client.get("/papers/999/translation").status_code == 404
    assert client.post("/papers/999/translation").status_code == 404


def test_prepare_keeps_svg_figures_as_img():
    # SVG の図は <object> で埋め込まれている。消さずに <img> にして、ほかの <object> は消す
    page = (
        '<html><body><div class="ltx_document"><figure id="S1.F1">'
        '<object type="image/svg+xml" data="2409.11136v1/fig.svg" id="S1.F1.g1" class="ltx_graphics" width="476"></object>'
        '<object type="application/x-shockwave-flash" data="evil.swf"></object>'
        "<figcaption>Figure 1: An illustration.</figcaption></figure></div></body></html>"
    )
    soup, _ = translation.prepare(page, "https://arxiv.org/html/2409.11136")
    out = str(soup)
    assert "<object" not in out and "evil.swf" not in out
    img = soup.find("img", id="S1.F1.g1")
    assert img["src"] == "https://arxiv.org/html/2409.11136v1/fig.svg" and img["width"] == "476"


def test_translation_disabled_without_translator(client, fake_sources, monkeypatch):
    # 公開版（翻訳サーバーが無い）では始められないことを、理由付きで返す
    monkeypatch.setattr(main, "TRANSLATOR_URL", "")
    p = add(client, "1706.03762")
    res = client.post(f"/papers/{p['id']}/translation")
    assert res.status_code == 503 and "翻訳を使えません" in res.json()["detail"]

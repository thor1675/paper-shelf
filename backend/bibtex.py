import re
import unicodedata

# キーに使わない、タイトルの先頭によく来る語（Google Scholar のキーと同じ考え方）
STOPWORDS = {"a", "an", "the", "on", "of", "in", "for", "to", "and", "with", "is", "are", "do", "does", "can", "how", "what", "when", "why", "not", "all", "be"}


def _ascii_word(s: str) -> str:
    """アクセントを外して英小文字だけにする（Schütze → schutze）"""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def cite_key(authors: list[str], year: int, title: str) -> str:
    """vaswani2017attention の形のキー"""
    last = _ascii_word(authors[0].split()[-1]) if authors else ""
    words = [_ascii_word(w) for w in re.split(r"[\s\-:]+", title)]
    first = next((w for w in words if w and w not in STOPWORDS), "")
    return f"{last or 'anon'}{year}{first}"


def _escape(s: str) -> str:
    # arXiv のタイトルはもともと LaTeX で書かれていることがある（$k$ など）ので、
    # 数式や命令は残し、本文で特別な意味を持つ & % # _ だけをエスケープする
    return re.sub(r"(?<!\\)([&%#_])", r"\\\1", s)


def to_bibtex(papers) -> str:
    """
    論文の list を BibTeX にする。
    研究室のテンプレートの junsrt は eprint 欄を表示しないので、
    Google Scholar と同じく journal に「arXiv preprint arXiv:番号」を入れる
    """
    used: dict[str, int] = {}
    entries = []
    for p in papers:
        key = cite_key(p.authors, p.published.year, p.title)
        # 同じキーが重なったら vaswani2017attentiona, ...b のように区別する
        n = used.get(key, 0)
        used[key] = n + 1
        if n:
            key += "abcdefghijklmnopqrstuvwxyz"[n - 1]
        entries.append(
            "\n".join(
                [
                    f"@article{{{key},",
                    f"  title = {{{{{_escape(p.title)}}}}},",
                    f"  author = {{{' and '.join(_escape(a) for a in p.authors)}}},",
                    f"  journal = {{arXiv preprint arXiv:{p.arxiv_id}}},",
                    f"  year = {{{p.published.year}}},",
                    f"  url = {{https://arxiv.org/abs/{p.arxiv_id}}}",
                    "}",
                ]
            )
        )
    return "\n\n".join(entries) + ("\n" if entries else "")

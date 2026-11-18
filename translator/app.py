"""
英語→日本語の翻訳だけをする小さな API。モデルは Hugging Face の FuguMT（staka/fugumt-en-ja、CC BY-SA 4.0）を
CTranslate2 の int8 に変換したもの。GPU の無い PC でも CPU で動く
"""

import os
import re
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

MODEL_DIR = os.environ.get("MODEL_DIR", "/model")
# 文の途中で切らないための略語（"et al. (2020)" や "Fig. 3" の後ろで文を分けない）
ABBREVIATIONS = {
    "e.g.", "i.e.", "et al.", "al.", "fig.", "figs.", "eq.", "eqs.", "sec.", "secs.", "tab.", "no.",
    "vs.", "etc.", "approx.", "cf.", "ref.", "refs.", "resp.", "dr.", "mr.", "ms.", "prof.", "st.", "vol.", "pp.",
}

_model = None
_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    # 最初の翻訳を待たせないよう、起動したら裏でモデルを読み込んでおく（11 秒ほどかかる）
    threading.Thread(target=model, daemon=True).start()
    yield


app = FastAPI(title="paper-shelf translator", lifespan=lifespan)


def model():
    """モデルは最初に使うときに 1 回だけ読み込む（起動を速くし、使わなければメモリも食わない）"""
    global _model
    with _lock:
        if _model is None:
            import ctranslate2
            from transformers import AutoTokenizer

            _model = (
                ctranslate2.Translator(f"{MODEL_DIR}/ct2", device="cpu", inter_threads=1, intra_threads=4),
                AutoTokenizer.from_pretrained(f"{MODEL_DIR}/tokenizer"),
            )
        return _model


def split_sentences(text: str) -> list[str]:
    """段落を文に分ける。FuguMT は 1 文ずつ訳す前提で学習されている"""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\[\"“⟦])", text.strip())
    sentences: list[str] = []
    for p in parts:
        words = sentences[-1].split() if sentences else []
        last = words[-1] if words else ""
        before = words[-2] if len(words) > 1 else ""
        # 名前の頭文字（"by A. Smith" の A.）。"propose X." のような文の終わりと区別するため、
        # 直前が by / and / & / カンマ / 別の頭文字のときだけ頭文字とみなす
        initial = re.fullmatch(r"[A-Z]\.", last) and (
            before.lower() in ("by", "and", "&") or before.endswith(",") or re.fullmatch(r"[A-Z]\.", before)
        )
        # 直前が略語や頭文字で終わっていたら、文の区切りではない
        if sentences and (last.lower() in ABBREVIATIONS or initial):
            sentences[-1] += " " + p
        else:
            sentences.append(p)
    return [s for s in sentences if s]


def translate_sentences(sentences: list[str]) -> list[str]:
    translator, tok = model()
    if not sentences:
        return []
    source = [tok.convert_ids_to_tokens(tok.encode(s, truncation=True, max_length=500)) for s in sentences]
    with _lock:  # CTranslate2 の 1 つのモデルを複数のリクエストで同時に使わない
        results = translator.translate_batch(source, beam_size=2, max_batch_size=16, max_decoding_length=512)
    return [tok.decode(tok.convert_tokens_to_ids(r.hypotheses[0]), skip_special_tokens=True) for r in results]


def translate_texts(texts: list[str]) -> list[str]:
    """段落の list を訳す。段落ごとに文に分けてまとめて訳し、段落に戻す"""
    sentences, owners = [], []
    for i, t in enumerate(texts):
        for s in split_sentences(t):
            sentences.append(s)
            owners.append(i)
    out = [""] * len(texts)
    for i, ja in zip(owners, translate_sentences(sentences)):
        out[i] += ja
    return out


class TranslateRequest(BaseModel):
    texts: list[str] = Field(max_length=200)


class TranslateResponse(BaseModel):
    texts: list[str]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/translate", response_model=TranslateResponse)
def translate(body: TranslateRequest):
    return TranslateResponse(texts=translate_texts(body.texts))

# 1 段目：Hugging Face の FuguMT（英→日）を CTranslate2 の形式に変換し、int8 に軽量化する。
# PyTorch はこの段でだけ使い、出来上がるイメージには入れない
FROM python:3.12-slim AS convert
RUN pip install --no-cache-dir uv==0.13.7 \
 && uv pip install --system --no-cache --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 \
 && uv pip install --system --no-cache transformers==4.57.6 sentencepiece==0.2.0 ctranslate2==4.8.3 protobuf==5.28.3
RUN ct2-transformers-converter --model staka/fugumt-en-ja --output_dir /model/ct2 --quantization int8 \
 && python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('staka/fugumt-en-ja').save_pretrained('/model/tokenizer')"

# 2 段目：変換済みのモデルと、動かすのに要る軽いライブラリだけ
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.7
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY --from=convert /model /model
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]

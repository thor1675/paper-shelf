FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv==0.13.7

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

# 起動のたびに未適用のマイグレーションを当ててから API を立ち上げる。
# PORT は Render などが渡す番号（無ければ 8000）。手元の Docker では compose が --reload 付きで上書きする
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]

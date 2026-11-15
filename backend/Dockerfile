FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv==0.13.7

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

# 起動のたびに未適用のマイグレーションを当ててから API を立ち上げる
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"]

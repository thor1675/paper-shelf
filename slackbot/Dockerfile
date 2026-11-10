FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

# -u: print をバッファせずにすぐログに出す
CMD ["python", "-u", "bot.py"]

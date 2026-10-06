from fastapi import FastAPI

app = FastAPI(title="paper-shelf API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

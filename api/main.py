from fastapi import FastAPI

app = FastAPI(title="Wardrobe Bot API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

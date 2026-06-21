from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Simple Svelte + Python App", version="0.1.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/hello")
async def hello(name: str = Query(default="World", max_length=80)) -> dict[str, str]:
    cleaned_name = name.strip() or "World"
    return {"message": f"Hello, {cleaned_name}! This response came from Python."}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:

    @app.get("/")
    async def frontend_not_built() -> dict[str, str]:
        return {
            "message": "The API is running. Build the Svelte frontend with `npm run build` in frontend/."
        }

from pathlib import Path

from litestar import Litestar, get
from litestar.static_files import create_static_files_router


@get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@get("/api/hello")
async def hello(name: str = "World") -> dict[str, str]:
    cleaned_name = name.strip() or "World"
    return {"message": f"Hello, {cleaned_name}! This response came from Python."}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if frontend_dist.is_dir():
    frontend = create_static_files_router(
        path="/",
        directories=[str(frontend_dist)],
        html_mode=True,
    )
else:

    @get("/")
    async def frontend_not_built() -> dict[str, str]:
        return {
            "message": "The API is running. Build the Svelte frontend with `npm run build` in frontend/."
        }

    frontend = frontend_not_built


app = Litestar(
    route_handlers=[health, hello, frontend],
    debug=False,
)

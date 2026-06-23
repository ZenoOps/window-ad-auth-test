from pathlib import Path

from litestar import Litestar, get
from litestar.response import File
from litestar.static_files import create_static_files_router

from app.auth import (
    casdoor_callback,
    current_user,
    local_login,
    logout,
    start_kerberos_login,
    verify_casdoor_token,
)


@get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@get("/api/hello")
async def hello(name: str = "World") -> dict[str, str]:
    cleaned_name = name.strip() or "World"
    return {"message": f"Hello, {cleaned_name}! This response came from Python."}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if frontend_dist.is_dir():

    @get("/login")
    async def local_login_page() -> File:
        return File(path=frontend_dist / "index.html", media_type="text/html")

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

    @get("/login")
    async def local_login_page() -> dict[str, str]:
        return {
            "message": "The API is running. Build the Svelte frontend with `npm run build` in frontend/."
        }


app = Litestar(
    route_handlers=[
        health,
        hello,
        start_kerberos_login,
        casdoor_callback,
        local_login,
        logout,
        verify_casdoor_token,
        current_user,
        local_login_page,
        frontend,
    ],
    debug=False,
)

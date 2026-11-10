"""The HTTP API. Read-only: no endpoint writes a file, takes a path, or runs
a command. No accounts, no cookies, no cross-origin access."""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from textchef import __version__
from textchef.config import Config
from textchef.server.index import Index, ScopeError
from textchef.server.themes import REPO, load_themes

WEB_DIST = REPO / "web" / "out"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Range(Strict):
    min: float | str | None = None
    max: float | str | None = None


class Scope(Strict):
    groups: list[str] | None = Field(None, max_length=500)
    topics: list[int] | None = Field(None, max_length=500)
    filters: dict[str, list[str] | Range] | None = None


class QueryBody(Strict):
    q: str = Field(max_length=2000)
    k: int = Field(50, ge=1, le=200)
    min_score: float = Field(0.3, ge=0, le=1)
    scope: Scope | None = None


class SimilarBody(Strict):
    row: int = Field(ge=0)
    k: int = Field(10, ge=1, le=100)


class RandomBody(Strict):
    n: int = Field(5, ge=1, le=50)
    min_words: int = Field(6, ge=0, le=1000)
    seed: int | None = None
    scope: Scope | None = None


class BrowseBody(Strict):
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)
    scope: Scope | None = None


class ScopeBody(Strict):
    scope: Scope | None = None


class TopicBody(Strict):
    limit: int = Field(30, ge=1, le=200)
    scope: Scope | None = None


class ContrastBody(Strict):
    a: Scope
    b: Scope | None = None
    within: Scope | None = None
    top: int = Field(15, ge=1, le=50)


def _dump(scope: Scope | None) -> dict | None:
    return scope.model_dump() if scope else None


_INLINE_SCRIPT = re.compile(rb"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>", re.S)


def content_security_policy(web_dir: Path | None) -> str:
    """Scripts and styles from this server only. The static export carries
    inline bootstrap scripts; each is allowed by its hash, nothing else inline."""
    hashes = set()
    if web_dir and web_dir.is_dir():
        for page in web_dir.rglob("*.html"):
            for body in _INLINE_SCRIPT.findall(page.read_bytes()):
                digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
                hashes.add(f"'sha256-{digest}'")
    return "; ".join([
        "default-src 'none'",
        " ".join(["script-src 'self'", *sorted(hashes)]),
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


def create_app(cfg: Config, web_dir: Path | None = WEB_DIST) -> FastAPI:
    index = Index(cfg)
    themes = load_themes(cfg.themes_dir)
    app = FastAPI(title="textchef", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None)
    # the server is for this machine only; refusing other Host headers blocks
    # DNS-rebinding pages from reading it through a browser
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    csp = content_security_policy(web_dir)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    api = APIRouter(prefix="/api")

    @app.exception_handler(ScopeError)
    async def bad_scope(_request, exc: ScopeError):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @api.get("/status")
    def status() -> dict:
        m = index.manifest
        return {"ready": True, "version": __version__,
                "n_rows": m["n_rows"], "n_unique": m["n_unique"], "n_topics": m["n_topics"],
                "duplicates_merged": m["duplicates_merged"],
                "model": m["model"], "has_id": m["has_id"], "has_group": m["has_group"],
                "group_label": cfg.group_label, "id_label": cfg.id_label,
                "theme_light": cfg.theme_light, "theme_dark": cfg.theme_dark}

    @api.get("/themes")
    def get_themes() -> dict:
        return {"themes": themes}

    @api.get("/graph")
    def graph() -> dict:
        return index.graph()

    @api.post("/facets")
    def facets(body: ScopeBody) -> dict:
        return index.facets(_dump(body.scope))

    @api.post("/query")
    def query(body: QueryBody) -> dict:
        return index.search(body.q, k=body.k, scope=_dump(body.scope), min_score=body.min_score)

    @api.post("/similar")
    def similar(body: SimilarBody) -> dict:
        out = index.similar(body.row, k=body.k)
        if out is None:
            raise HTTPException(404, "no such row")
        return out

    @api.post("/random")
    def random(body: RandomBody) -> dict:
        return index.random(n=body.n, scope=_dump(body.scope), min_words=body.min_words,
                            seed=body.seed)

    @api.post("/browse")
    def browse(body: BrowseBody) -> dict:
        return index.browse(scope=_dump(body.scope), offset=body.offset, limit=body.limit)

    @api.post("/topic/{tid}")
    def topic(tid: int, body: TopicBody) -> dict:
        out = index.topic_detail(tid, scope=_dump(body.scope), limit=body.limit)
        if out is None:
            raise HTTPException(404, "no such topic")
        return out

    @api.post("/contrast")
    def contrast(body: ContrastBody) -> dict:
        return index.contrast(_dump(body.a), _dump(body.b), within=_dump(body.within),
                              top=body.top)

    @api.get("/document/{row}")
    def document(row: int) -> dict:
        out = index.document(row)
        if out is None:
            raise HTTPException(404, "no such document")
        return out

    app.include_router(api)
    # the built web app; StaticFiles refuses paths that leave its folder
    if web_dir and (web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app

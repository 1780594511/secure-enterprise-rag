import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Path as RoutePath, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .adapters import configured_generator
from .corpus import ACCOUNTS, DEPARTMENTS, DEMO_PASSWORD
from .ingest import decode_upload
from .service import Service
from .store import ALLOWED, Fault, Store, digest, identifier

ROOT = Path(__file__).resolve().parents[1]
COOKIE = "serag_session"
Resource = Annotated[str, RoutePath(pattern=r"^[A-Za-z0-9._-]{1,100}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class Question(Input):
    question: str = Field(min_length=1, max_length=1000)


class Upload(Input):
    filename: str = Field(min_length=1, max_length=140, pattern=r"^[^/\\\x00-\x1f]+$")
    content_b64: str = Field(min_length=1, max_length=2796204)


class Rules(Input):
    public: bool = False
    departments: list[str] = Field(default_factory=list, max_length=12)
    users: list[str] = Field(default_factory=list, max_length=30)


class Import(Upload, Rules):
    title: str = Field(min_length=1, max_length=120)
    dept: str = Field(min_length=1, max_length=50)


def token(request: Request):
    return request.cookies.get(COOKIE, "")


Session = Annotated[str, Depends(token)]


def create_app(path=None, generator=None, cache=True):
    load_dotenv(ROOT / ".env")
    store = Store(path or os.getenv("RAG_DB") or ROOT / "var" / "knowledge.db")
    service = Service(store, generator or configured_generator(), cache)

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        yield

    app = FastAPI(title="Secure Enterprise RAG", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.service = service
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"]
    )

    @app.middleware("http")
    async def security(request, call_next):
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.headers.get("x-rag-request") != "1"
        ):
            response = JSONResponse({"detail": "缺少同源请求头"}, status_code=403)
        elif int(request.headers.get("content-length") or 0) > 2_810_000:
            response = JSONResponse({"detail": "请求过大"}, status_code=413)
        else:
            response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store, private",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    @app.exception_handler(Fault)
    async def fail(request, exc):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"detail": "请求字段、资源标识或文件大小无效"}, status_code=422)

    @app.get("/api/demo")
    def demo():
        return {
            "accounts": [{"uid": u, "name": n, "role": r, "dept": d} for u, n, r, d in ACCOUNTS],
            "password": DEMO_PASSWORD,
            "departments": sorted(DEPARTMENTS),
        }

    @app.post("/api/login")
    def login(body: Login, response: Response, session: Session):
        fresh = store.login(body.username, body.password)
        with store.transaction(True) as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (digest(session),))
        response.set_cookie(COOKIE, fresh, httponly=True, samesite="strict", max_age=28800, path="/")
        return {"ok": True}

    @app.post("/api/logout")
    def logout(session: Session, response: Response):
        with store.transaction(True) as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (digest(session),))
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(session: Session):
        with store.transaction() as db:
            return {
                **store.identity(db, session),
                "epoch": store.epoch(db),
                "model": service.generator.name,
            }

    @app.get("/api/documents")
    def documents(session: Session):
        return service.guarded(session, "catalog", store.list_docs)

    @app.get("/api/admin/documents")
    def management(session: Session):
        return service.guarded(
            session, "manage-list", lambda db, u: store.list_docs(db, u, True), admin=True
        )

    @app.post("/api/admin/documents")
    def upload(body: Import, session: Session):
        doc = identifier()

        def save(db, user):
            store.insert(
                db,
                id=doc,
                owner=user["uid"],
                raw=decode_upload(body.content_b64),
                **body.model_dump(exclude={"content_b64"}),
            )
            store.invalidate(db)
            return {"id": doc}

        return service.guarded(session, "import", save, True, {"doc": doc})

    def mutate(session, doc, action, data):
        def change(db, user):
            if "content_b64" in data:
                data["raw"] = decode_upload(data.pop("content_b64"))
            store.change(db, doc, action, **data)
            return {"ok": True, "epoch": store.epoch(db)}

        return service.guarded(session, action, change, True, {"doc": doc})

    @app.put("/api/admin/documents/{doc}/acl")
    def acl(doc: Resource, body: Rules, session: Session):
        return mutate(session, doc, "acl", body.model_dump())

    @app.put("/api/admin/documents/{doc}")
    def update(doc: Resource, body: Upload, session: Session):
        return mutate(session, doc, "update", body.model_dump())

    @app.delete("/api/admin/documents/{doc}")
    def delete(doc: Resource, session: Session):
        return mutate(session, doc, "delete", {})

    @app.get("/api/documents/{doc}/versions/{version}/download")
    def download(doc: Resource, version: int, session: Session):
        def read(db, user):
            row = db.execute(
                "SELECT filename,original FROM docs d WHERE id=:doc AND version=:v AND " + ALLOWED,
                {**user, "doc": doc, "v": version},
            ).fetchone()
            if not row:
                raise Fault(404, "资料不可用或版本已变更")
            return Response(
                row["original"],
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''"
                    + quote(row["filename"], safe="")
                },
            )

        return service.guarded(session, "download", read, resource={"doc": doc, "version": version})

    @app.get("/api/references/{cid}")
    def reference(cid: Resource, session: Session):
        return service.guarded(
            session, "reference", lambda db, u: store.evidence(db, u, [cid])[0], resource={"chunk": cid}
        )

    @app.post("/api/query")
    def ask(body: Question, session: Session):
        return service.ask(session, body.question)

    @app.get("/api/history")
    def history(session: Session):
        return service.guarded(session, "history", service.history)

    @app.get("/api/admin/audit")
    def audit(session: Session):
        def read(db, user):
            return [
                {**dict(r), "refs": json.loads(r["refs"])}
                for r in db.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT 150")
            ]

        return service.guarded(session, "audit", read, True)

    @app.post("/api/admin/evaluate")
    def evaluate(session: Session):
        service.guarded(session, "evaluation-start", lambda db, u: None, True)
        from evaluations.run import run_suite

        result = run_suite("dev")
        return service.guarded(session, "evaluation-result", lambda db, u: result, True)

    dist = ROOT / "frontend" / "dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    @app.get("/source/{cid}")
    def home():
        if not (dist / "index.html").is_file():
            raise Fault(503, "请先按 README 构建前端")
        return FileResponse(dist / "index.html")

    return app

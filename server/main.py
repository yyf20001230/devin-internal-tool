"""HTTP API. Every endpoint is generic - adding a tool never touches this file."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import Engine, Forbidden, Invalid, NotFound
from .spec import ToolSpec, User, load_directory, load_tools

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(os.environ.get("TOOLS_DIR", ROOT / "tools"))
DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "data.db"))


class ActionBody(BaseModel):
    record_id: int
    comment: str | None = None


def build_app(tools_dir: Path = TOOLS_DIR, db_path: Path | str = DB_PATH) -> FastAPI:
    tools = load_tools(tools_dir)
    directory = load_directory(tools_dir)
    engine = Engine(db_path, tools)

    app = FastAPI(title="Internal Tools Platform")
    app.state.engine = engine
    app.state.directory = directory
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(Forbidden)
    async def _forbidden(_: Request, e: Forbidden):
        raise HTTPException(403, str(e))

    @app.exception_handler(NotFound)
    async def _notfound(_: Request, e: NotFound):
        raise HTTPException(404, str(e))

    @app.exception_handler(Invalid)
    async def _invalid(_: Request, e: Invalid):
        raise HTTPException(400, str(e))

    # Auth is a stub: the front-end sends X-User. In production this is an OIDC/Entra ID
    # token validated by the reverse proxy, and roles come from group claims.
    def current_user(x_user: str = Header(default="")) -> User:
        user = next((u for u in directory.users if u.id == x_user), None)
        if user is None:
            raise HTTPException(401, "unknown user")
        return user

    def tool(tool_id: str, user: User = Depends(current_user)) -> ToolSpec:
        spec = tools.get(tool_id)
        if spec is None:
            raise HTTPException(404, f"tool {tool_id}")
        engine.require(spec, user, "read")
        return spec

    @app.get("/api/me")
    def me(user: User = Depends(current_user)):
        return {"user": user, "roles": directory.roles, "tools": [
            {"id": t.id, "name": t.name, "app": t.app, "description": t.description,
             "can": {op: bool(set(user.roles) & set(getattr(t.permissions, op)))
                     for op in ("read", "create", "update", "export")}}
            for t in engine.visible_tools(user)
        ]}

    @app.get("/api/users")
    def users():
        return directory.users  # the role switcher for the demo

    @app.get("/api/tools/{tool_id}")
    def get_tool(spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        can = lambda roles: bool(set(user.roles) & set(roles))  # noqa: E731
        d = spec.model_dump()
        for f in d["fields"]:
            f["masked"] = f["visible_to"] is not None and not can(f["visible_to"])
        for a in d["actions"]:
            a["allowed"] = can(a["roles"])
        d["can"] = {op: can(getattr(spec.permissions, op)) for op in ("read", "create", "update", "export")}
        return d

    @app.get("/api/tools/{tool_id}/records")
    def list_records(spec: ToolSpec = Depends(tool), user: User = Depends(current_user),
                     view: str | None = None, q: str = ""):
        return engine.list_records(spec, user, view, q)

    @app.get("/api/tools/{tool_id}/records.csv", response_class=PlainTextResponse)
    def export(spec: ToolSpec = Depends(tool), user: User = Depends(current_user), view: str | None = None):
        return engine.export_csv(spec, user, view)

    @app.post("/api/tools/{tool_id}/records", status_code=201)
    def create(values: dict, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.create_record(spec, user, values)

    @app.get("/api/tools/{tool_id}/records/{rid}")
    def get_record(rid: int, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.get_record(spec, user, rid)

    @app.patch("/api/tools/{tool_id}/records/{rid}")
    def update(rid: int, values: dict, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.update_record(spec, user, rid, values)

    @app.post("/api/tools/{tool_id}/actions/{action_id}")
    def action(action_id: str, body: ActionBody, spec: ToolSpec = Depends(tool),
               user: User = Depends(current_user)):
        return engine.run_action(spec, user, action_id, body.record_id, body.comment)

    @app.get("/api/tools/{tool_id}/dashboard")
    def dashboard(spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.dashboard(spec, user)

    @app.get("/api/tools/{tool_id}/audit")
    def audit(spec: ToolSpec = Depends(tool), user: User = Depends(current_user),
              record_id: int | None = Query(default=None)):
        return engine.audit(spec, user, record_id)

    @app.get("/api/tools/{tool_id}/integrations")
    def integrations(spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.integrations(spec, user)

    dist = ROOT / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = build_app()
